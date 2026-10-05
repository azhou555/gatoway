import os
from pathlib import Path
import subprocess

import pytest

from gatoway.code_grader import CodeGrader, CodeInfrastructureError, extract_code, parse_score
from gatoway.coding_tasks import load_tasks, fenced_reference

FENCE = chr(96) * 3


def block(code, language=""):
    return f"{FENCE}{language}\n{code}\n{FENCE}"


def test_extract_last_matching_block_else_last_untagged():
    response = block("first", "python") + block("untagged") + block("last", "py")
    assert extract_code(response, "python") == "last"
    assert extract_code(block("first") + block("last"), "typescript") == "last"
    assert extract_code(block("export const x=1;", "ts"), "typescript") == "export const x=1;"
    assert extract_code("plain text", "python") is None


@pytest.mark.parametrize("language,output,returncode,expected", [
    ("python", "Ran 10 tests in 0.001s\n\nFAILED (failures=2, errors=1)", 1, .7),
    ("python", "Ran 1 test in 0.001s\n\nOK", 0, 1),
    ("python", "Ran 2 tests in 0.1s\n\nOK (skipped=1)", 0, .5),
    ("python", "Ran 10 tests in 0.1s\n\nOK", 137, 0),
    ("python", "Traceback", 1, 0),
    ("typescript", "# tests 10\n# pass 7\n# fail 3\n", 1, .7),
    ("typescript", "# tests 3\n# pass 3\n# fail 0\n", 0, 1),
    ("typescript", "# tests 0\n# pass 0\n# fail 0\n", 0, 0),
    ("typescript", "syntax error", 1, 0),
])
def test_partial_credit_and_crashes(language, output, returncode, expected):
    assert parse_score(language, output, returncode) == expected


def test_missing_code_does_not_start_docker():
    def forbidden(*args, **kwargs):
        pytest.fail("runner called")
    assert CodeGrader(runner=forbidden).grade("no code", Path("."), "python") == 0


def test_fake_runner_sees_isolation_and_partial_credit(tmp_path):
    (tmp_path / "test_hidden.py").write_text("# trusted test")
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "sha256:test\n", "")
        if command[1] == "rm":
            return subprocess.CompletedProcess(command, 0, "", "")
        for value in ("--read-only", "--network", "none", "--cap-drop", "ALL",
                      "no-new-privileges", "--pids-limit", "--memory", "--cpus", "65534:65534"):
            assert value in command
        mount = command[command.index("-v")+1]
        workspace = Path(mount.removesuffix(":/workspace:ro"))
        assert (workspace / "solution.py").read_text() == "pass"
        assert (workspace / "test_hidden.py").exists()
        return subprocess.CompletedProcess(command, 1, "", "Ran 4 tests in 0.1s\nFAILED (failures=1)")
    assert CodeGrader(runner=runner).grade(block("pass", "py"), tmp_path, "python") == .75
    assert calls[-1][1:3] == ["rm", "-f"]


@pytest.mark.parametrize("failure", ["missing", "daemon", "runtime", "timeout"])
def test_infrastructure_and_timeout(tmp_path, failure):
    (tmp_path / "test_hidden.py").write_text("")
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if command[1] == "rm":
            return subprocess.CompletedProcess(command, 0, "", "")
        if failure == "missing":
            raise FileNotFoundError("docker")
        if command[1] == "image":
            return subprocess.CompletedProcess(command, 1 if failure == "daemon" else 0, "image", "")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(command, 125, "", "daemon failed")
    grader = CodeGrader(runner=runner)
    if failure == "timeout":
        assert grader.grade(block("pass", "py"), tmp_path, "python") == 0
        assert calls[-1][1] == "rm"
    else:
        with pytest.raises(CodeInfrastructureError):
            grader.grade(block("pass", "py"), tmp_path, "python")


@pytest.mark.skipif(os.getenv("GATOWAY_DOCKER_TESTS") != "1", reason="opt-in Docker")
@pytest.mark.parametrize("language", ["python", "typescript"])
def test_real_docker_reference_and_wrong_answer(language):
    task = next(t for t in load_tasks("eval") if t.language == language)
    grader = CodeGrader()
    assert grader.grade(fenced_reference(task), task.directory, language) == 1
    assert grader.grade(block("invalid code!", language), task.directory, language) == 0


@pytest.mark.skipif(os.getenv("GATOWAY_DOCKER_TESTS") != "1", reason="opt-in Docker")
def test_legacy_live_loop_also_runs_in_docker():
    grader = CodeGrader()
    assert grader.grade_loop("for i in range(n): print(arr[i])") == 1
    assert grader.grade_loop("for i in range(1,n): print(arr[i])") == 0
    fixtures = (([1, 2], [(1,)]), ([3], []), ([], []))
    assert grader.grade_loop("for i in range(n-1): print(arr[i])", fixtures) == 1


def test_typescript_preflight_falls_back_when_node22_cannot_transform():
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if command[1] == "image":
            return subprocess.CompletedProcess(command, 0, command[-1], "")
        if command[1] == "rm":
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 1 if "node:22-slim" in command else 0, "", "")
    grader = CodeGrader(runner=runner)
    grader.preflight("typescript")
    assert grader.images["typescript"] == "node:24-slim"
    assert any("node:22-slim" in command for command in calls)
