"""Only checked-in, trusted references run on the host; model output never does."""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from gatoway.coding_tasks import load_tasks
from gatoway.code_grader import parse_score, test_command as runner_command, TEST_FILES, EXTENSIONS

TASKS = load_tasks("eval") + load_tasks("train")
CODE = [task for task in TASKS if task.language != "design"]


def run_reference(tmp_path, source, target):
    language = target.language
    if language == "typescript" and not shutil.which("node"):
        pytest.skip("Node is not installed")
    suffix = EXTENSIONS[language]
    reference = source.reference
    if source.entrypoint != target.entrypoint:
        if language == "python":
            reference += f"\n{target.entrypoint} = {source.entrypoint}\n"
        else:
            reference += f"\nexport {{ {source.entrypoint} as {target.entrypoint} }};\n"
    (tmp_path / f"solution.{suffix}").write_text(reference)
    shutil.copyfile(target.directory / TEST_FILES[language], tmp_path / TEST_FILES[language])
    command = runner_command(language)
    if language == "python":
        command[0] = sys.executable
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    return result, parse_score(language, result.stdout + "\n" + result.stderr, result.returncode)


@pytest.mark.parametrize("task", CODE, ids=lambda task: task.task_id)
def test_reference_passes_own_hidden_tests(tmp_path, task):
    result, score = run_reference(tmp_path, task, task)
    assert result.returncode == 0, result.stdout + result.stderr
    assert score == 1.0


PAIRS = [(source, target) for source in CODE for target in CODE
         if source.split != target.split and source.language == target.language]


@pytest.mark.parametrize("source,target", PAIRS,
                         ids=[f"{a.task_id}-against-{b.task_id}" for a,b in PAIRS])
def test_cross_split_references_fail_after_entrypoint_rebind(tmp_path, source, target):
    result, score = run_reference(tmp_path, source, target)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert score < 1.0
    assert "cannot import name" not in output
    assert "does not provide an export" not in output
    assert "ModuleNotFoundError" not in output


def test_artifact_metadata_and_rubrics():
    assert len(TASKS) == 24
    assert len({task.task_id for task in TASKS}) == len(TASKS)
    for task in TASKS:
        if task.language == "design":
            assert 4 <= len(task.rubric) <= 6
        else:
            assert task.entrypoint


def test_rpn_accepts_signed_zero_as_numeric_zero(tmp_path):
    from dataclasses import replace
    task = next(task for task in CODE if task.task_id == "evaluate_rpn")
    # A normal Math.trunc-based solution returns -0 for 1 / -2.
    reference = task.reference.replace(
        "const result=stack[0]; return result===0?0:result;", "return stack[0];"
    )
    assert reference != task.reference
    result, score = run_reference(tmp_path, replace(task, reference=reference), task)
    assert result.returncode == 0, result.stdout + result.stderr
    assert score == 1.0
