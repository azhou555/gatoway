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
    assert by_task["quadratic_roots"].tier == "medium"
    assert by_task["sql_query"].tier == "frontier"


@pytest.mark.asyncio
async def test_three_stable_runs_pass_gate_and_report_ranges():
    runs = await run_eval_repeated(dry_run=True, pool=None, runs=3)

    passed, detail = stability_gate(runs)
    report = build_report(runs, dry_run=True, db_backed=True, bank_rows=24)

    assert passed is True
    assert "all six" in detail
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
        await eval_module._real_provider("cheap", BENCHMARK_TASKS[0])
    assert attempts == 2
