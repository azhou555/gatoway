import subprocess
import sys
from pathlib import Path

import pytest

from gatoway.agentic_eval import (
    AgentResponse,
    DockerGrader,
    GradeResult,
    apply_model_patch,
    build_report,
    call_agentic_model,
    load_tasks,
    materialize_task,
    production_readiness_gate,
    run_agentic_task,
    scripted_repair_model,
    validate_patch,
)
from gatoway.providers import ProviderResponse, TIER_MODELS


def _trusted_local_grader(workspace: Path) -> GradeResult:
    """Run only repository-owned oracle code; generated code uses Docker."""
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "grader_tests", "-v"],
        cwd=workspace,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return GradeResult(result.returncode == 0, result.stdout + result.stderr)


def test_loads_three_escalating_tasks():
    tasks = load_tasks()

    assert [task.task_id for task in tasks] == [
        "dependency_planner",
        "ttl_cache",
        "webhook_idempotency",
    ]
    assert {task.task_id: task.difficulty for task in tasks} == {
        "dependency_planner": 0.68,
        "ttl_cache": 0.58,
        "webhook_idempotency": 0.82,
    }
    assert all(task.max_turns == 3 for task in tasks)


@pytest.mark.parametrize("task", load_tasks(), ids=lambda task: task.task_id)
def test_oracle_patches_pass_held_out_tests(task, tmp_path):
    materialize_task(task, tmp_path)

    patch = apply_model_patch(tmp_path, task.oracle_patch, task.editable_files)
    grade = _trusted_local_grader(tmp_path)

    assert patch.applied, patch.observation
    assert grade.passed, grade.output


def test_patch_validation_rejects_traversal_and_test_edits():
    traversal = "--- a/cache.py\n+++ b/../../outside.py\n@@ -1 +1 @@\n-old\n+new\n"
    test_edit = (
        "--- a/grader_tests/test_cache.py\n+++ b/grader_tests/test_cache.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
    )

    with pytest.raises(ValueError, match="unsafe patch path"):
        validate_patch(traversal, ("cache.py",))
    with pytest.raises(ValueError, match="non-editable"):
        validate_patch(test_edit, ("cache.py",))


async def test_failed_attempt_chains_observation_and_promotes_tier():
    task = next(task for task in load_tasks() if task.task_id == "ttl_cache")
    calls = []

    async def recording_model(task, tier, messages, turn):
        calls.append((tier, [dict(message) for message in messages], turn))
        return await scripted_repair_model(task, tier, messages, turn)

    async def threshold_router(task, observation, pool, threshold):
        del task, pool
        if threshold == 0.5:
            assert observation == ""
            return "medium"
        assert "No unified diff" in observation
        return "frontier"

    result = await run_agentic_task(
        task,
        pool=None,
        grader=_trusted_local_grader,
        model_caller=recording_model,
        route_turn=threshold_router,
    )

    assert result.passed
    assert result.tiers == ("medium", "frontier")
    assert result.tier_switches == 1
    assert len(calls) == 2
    assert "No unified diff" in calls[1][1][-1]["content"]
    assert "Current repository" in calls[1][1][-1]["content"]


def test_docker_grader_uses_isolation_flags(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    grade = DockerGrader()(tmp_path)

    assert grade.passed
    command = captured["command"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop") : command.index("--cap-drop") + 2
    ]
    assert f"{tmp_path.resolve()}:/workspace:ro" in command


def test_docker_preflight_pins_runtime_to_inspected_image(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "sha256:fixed\n", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    grader = DockerGrader()
    grader.preflight()
    grader(tmp_path)

    assert grader.image_id == "sha256:fixed"
    assert "sha256:fixed" in calls[-1]


async def test_report_labels_dry_run_as_non_quality_result():
    task = next(task for task in load_tasks() if task.task_id == "ttl_cache")

    async def medium_router(task, observation, pool, threshold):
        del task, observation, pool, threshold
        return "medium"

    result = await run_agentic_task(
        task,
        pool=None,
        grader=_trusted_local_grader,
        model_caller=scripted_repair_model,
        route_turn=medium_router,
    )
    report = build_report([[result]], dry_run=True, db_backed=False)

    assert "scripted repair smoke test" in report
    assert "not a model-quality result" in report
    assert "medium → medium" in report
    assert "Production readiness gate: FAIL" in report


def test_readiness_gate_requires_three_reliable_runs_without_provider_exhaustion():
    from gatoway.agentic_eval import AgenticAttempt, AgenticResult

    passing_attempt = AgenticAttempt(
        turn=1,
        threshold=0.5,
        tier="medium",
        model_id="openai/qwen3-small",
        cost_cents=0.1,
        input_tokens=10,
        output_tokens=10,
        latency_seconds=1.0,
        patch_applied=True,
        tests_passed=True,
        observation="ok",
    )
    runs = [[AgenticResult("task", True, (passing_attempt,))] for _ in range(3)]

    assert production_readiness_gate(runs) == (
        True,
        "every task passed at least 2/3 with no exhausted tier",
    )


async def test_provider_failure_uses_configured_tier_fallback(monkeypatch):
    task = next(task for task in load_tasks() if task.task_id == "ttl_cache")
    called = []

    async def fake_provider(model, messages, **kwargs):
        del messages, kwargs
        called.append(model)
        if len(called) == 1:
            raise RuntimeError("primary unavailable")
        return ProviderResponse("patch", model, 10, 5, 0.01, raw=None)

    monkeypatch.setattr("gatoway.agentic_eval.call_provider", fake_provider)
    response = await call_agentic_model(task, "medium", [], 1)

    assert called == TIER_MODELS["medium"][:2]
    assert response.content == "patch"
    assert response.model_id == TIER_MODELS["medium"][1]
    assert response.provider_error is None


async def test_exhausted_tier_fallback_becomes_observable_attempt(monkeypatch):
    task = next(task for task in load_tasks() if task.task_id == "ttl_cache")

    async def failed_provider(model, messages, **kwargs):
        del model, messages, kwargs
        raise RuntimeError("unavailable")

    async def medium_router(task, observation, pool, threshold):
        del task, observation, pool, threshold
        return "medium"

    monkeypatch.setattr("gatoway.agentic_eval.call_provider", failed_provider)
    result = await run_agentic_task(
        task,
        pool=None,
        grader=_trusted_local_grader,
        model_caller=call_agentic_model,
        route_turn=medium_router,
    )

    assert not result.passed
    assert len(result.attempts) == task.max_turns
    assert all("Provider call failed" in attempt.observation for attempt in result.attempts)
    assert all(attempt.model_id == "provider-error/medium" for attempt in result.attempts)
