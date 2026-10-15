"""Execution-based scoring for the two benchmark tasks with checkable answers."""

import asyncio

import pytest

import gatoway.eval as eval_module
from gatoway.eval import (
    BENCHMARK_TASKS,
    DEFAULT_THRESHOLD,
    build_report,
    run_eval,
    run_eval_repeated,
    score_python_execution,
    score_sql_execution,
    score_task,
    stability_gate,
)
from gatoway.providers import ProviderResponse


@pytest.mark.parametrize(
    "response",
    [
        "```python\nfor i in range(0, n): print(arr[i])\n```",
        "Use `for i in range(n): print(arr[i])`.",
        "for item in arr: print(item)",
        "for value in arr: print(value)",
    ],
)
def test_python_execution_accepts_good_answers(response):
    assert score_python_execution(response) == 1.0


@pytest.mark.parametrize(
    "response",
    [
        "for i in range(1, n): print(arr[i])",
        "for i in range(0, n - 1): print(arr[i])",
        "import os\nfor i in range(n): print(arr[i])",
        "Start the loop at zero.",
    ],
)
def test_python_execution_rejects_bad_or_unsafe_answers(response):
    assert score_python_execution(response) == 0.0


@pytest.mark.parametrize(
    "response",
    [
        "```sql\nSELECT DISTINCT salary FROM employees "
        "ORDER BY salary DESC LIMIT 1 OFFSET 1;\n```",
        "SELECT MAX(salary) FROM employees WHERE salary < "
        "(SELECT MAX(salary) FROM employees);",
    ],
)
def test_sql_execution_accepts_good_answers(response):
    assert score_sql_execution(response) == 1.0


@pytest.mark.parametrize(
    "response",
    [
        "SELECT salary FROM employees ORDER BY salary DESC LIMIT 1 OFFSET 1;",
        "SELECT MAX(salary) FROM employees;",
        "DELETE FROM employees;",
        "Use ORDER BY and LIMIT.",
    ],
)
def test_sql_execution_rejects_bad_answers(response):
    assert score_sql_execution(response) == 0.0


def test_benchmark_tasks_dispatch_to_execution_scorers():
    tasks = {task.task_id: task for task in BENCHMARK_TASKS}

    assert tasks["code_fix"].scoring_method == "python_execution"
    assert score_task(
        tasks["code_fix"], "for i in range(n): print(arr[i])"
    ) == 1.0

    assert tasks["sql_query"].scoring_method == "sql_execution"
    assert score_task(
        tasks["sql_query"],
        "SELECT DISTINCT salary FROM employees ORDER BY salary DESC LIMIT 1 OFFSET 1;",
    ) == 1.0


@pytest.mark.asyncio
async def test_eval_is_a_session_and_threshold_shift_changes_later_routing():
    router_results, _ = await run_eval(dry_run=True, pool=None)
    by_task = {result.task_id: result for result in router_results}

    assert router_results[0].current_threshold == DEFAULT_THRESHOLD
    assert router_results[-1].current_threshold > DEFAULT_THRESHOLD
    # Both tasks route lower at the default threshold. Their later turn
    # positions promote them, proving the session signal reaches the router.
    assert by_task["quadratic_roots"].tier == "gpt-oss"
    assert by_task["sql_query"].tier == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_three_stable_runs_pass_gate_and_report_ranges():
    runs = await run_eval_repeated(dry_run=True, pool=None, runs=3)

    passed, detail = stability_gate(runs)
    report = build_report(runs, dry_run=True, db_backed=True, bank_rows=24)

    assert passed is True
    assert "all 12" in detail
    assert "**Stability gate: PASS**" in report
    assert "Headline across 3 runs" in report
    assert "Session totals (mean and range)" in report
    assert "DB-backed pgvector" in report
    assert "24 rows" in report
    # Open-ended scores always disclose a range, even when all three canned
    # runs happen to be identical.
    assert "1.00 (1.00–1.00)" in report


@pytest.mark.asyncio
async def test_changed_checkable_score_fails_stability_gate():
    runs = await run_eval_repeated(dry_run=True, pool=None, runs=3)
    runs[-1].router_results[0].score = 0.0

    passed, detail = stability_gate(runs)

    assert passed is False
    assert "router/capital_france" in detail


@pytest.mark.asyncio
async def test_live_provider_call_has_a_bounded_timeout(monkeypatch):
    attempts = 0

    async def never_returns(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        assert kwargs["temperature"] == 0.0
        assert kwargs["max_tokens"] == 512
        await asyncio.sleep(1)
        return ProviderResponse("", "", 0, 0, 0.0, None)

    monkeypatch.setattr(eval_module, "call_provider", never_returns)
    monkeypatch.setattr(eval_module, "EVAL_PROVIDER_TIMEOUT_SECONDS", 0.001)

    with pytest.raises(TimeoutError):
        await eval_module._real_provider("gemma-small", BENCHMARK_TASKS[0])
    assert attempts == 2


async def test_coding_suite_starts_a_fresh_session():
    router, baseline = await run_eval(dry_run=True, pool=None)
    assert len(router) == len(baseline) == 16
    original = [result for result in router if result.suite == "original"]
    coding = [result for result in router if result.suite == "coding"]
    assert len(original) == len(coding) == 8
    assert coding[0].current_threshold == original[0].current_threshold == DEFAULT_THRESHOLD
    assert [r.current_threshold for r in coding] == [r.current_threshold for r in original]


async def test_code_gate_compares_full_pass_not_partial_credit():
    runs = await run_eval_repeated(dry_run=True, pool=None, runs=3)
    for run, value in zip(runs, [.7, .8, .5]):
        next(r for r in run.router_results if r.task_id == "two_sum_pairs").score = value
    assert stability_gate(runs)[0]
    next(r for r in runs[-1].router_results if r.task_id == "two_sum_pairs").score = 1.0
    assert not stability_gate(runs)[0]


async def test_live_dispatch_uses_actual_model_and_propagates_infrastructure(monkeypatch):
    from gatoway.bank_corpus import score
    import gatoway.judge as judge_module
    from gatoway.code_grader import CodeInfrastructureError

    seen = []
    async def fake_judge(prompt, response, rubric, answer_model):
        seen.append(answer_model)
        assert rubric
        return .75
    monkeypatch.setattr(judge_module, "judge", fake_judge)
    task = next(t for t in BENCHMARK_TASKS if t.task_id == "auth_extraction")
    assert await score(task, "answer", "openai/glm-5") == .75
    assert seen == ["openai/glm-5"]
    with pytest.raises(ValueError, match="live rubric"):
        score_task(task, "answer")

    class FailedGrader:
        def grade(self, *args):
            raise CodeInfrastructureError("Docker stopped")
    task = next(t for t in BENCHMARK_TASKS if t.scoring_method == "code_tests")
    with pytest.raises(CodeInfrastructureError):
        await score(task, "answer", "openai/gpt-oss", grader=FailedGrader())


async def test_report_discloses_suites_and_new_baseline():
    runs = await run_eval_repeated(dry_run=True, pool=None, runs=1)
    report = build_report(runs, dry_run=True, db_backed=False)
    assert "two independent eight-turn sessions" in report
    assert "Per-suite results" in report
    assert "not comparable to historical eight-task gates" in report
    assert "| coding/1 |" in report
    assert "| original/1 |" in report
    assert "scripted coding scores" in report


async def test_live_legacy_python_dispatch_never_executes_on_host():
    from gatoway.bank_corpus import score
    calls = []
    class FakeGrader:
        def grade_loop(self, response, fixtures):
            calls.append(response)
            return 1.0
    task = next(t for t in BENCHMARK_TASKS if t.task_id == "code_fix")
    assert await score(task, "model code", "openai/gpt-oss", grader=FakeGrader()) == 1
    assert calls == ["model code"]


async def test_strict_eval_never_approximates_database_failure(monkeypatch):
    import gatoway.router
    async def fail(*args):
        raise RuntimeError("database disconnected")
    monkeypatch.setattr(gatoway.router, "classify", fail)
    with pytest.raises(RuntimeError, match="database disconnected"):
        await eval_module.pick_router_tier(BENCHMARK_TASKS[0], object(), require_db=True)
    with pytest.raises(RuntimeError, match="working database"):
        await eval_module.pick_router_tier(BENCHMARK_TASKS[0], None, require_db=True)


async def test_eval_checkpoint_records_completed_runs(tmp_path):
    import json
    checkpoint = tmp_path / "results.json"
    await run_eval_repeated(True, None, 1, checkpoint=checkpoint)
    payload = json.loads(checkpoint.read_text())
    assert payload["dry_run"]
    assert not payload["require_db"]
    assert len(payload["runs"][0]["router_results"]) == 16


def test_exact_match_accepts_unicode_mathematical_minus():
    assert eval_module.score_exact_match("The answer is −10°C.", ["-10"]) == 1.0
    assert eval_module.score_exact_match("The answer is 10°C.", ["-10"]) == 0.0
