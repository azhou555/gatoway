from collections import Counter

import pytest

from gatoway.bank_corpus import TRAIN_PROMPTS, assert_no_eval_overlap, score
from gatoway.eval import BENCHMARK_TASKS, score_task


def test_corpus_structure_and_separation():
    assert len(TRAIN_PROMPTS) == 36
    ids = [task.prompt_id for task in TRAIN_PROMPTS]
    assert len(set(ids)) == len(ids)
    assert set(ids).isdisjoint(task.task_id for task in BENCHMARK_TASKS)
    assert Counter(task.neighborhood for task in TRAIN_PROMPTS) == {
        "factual recall": 3, "arithmetic": 3, "unit conversion": 2,
        "algebra": 2, "loop/off-by-one fixes": 3, "SQL aggregate queries": 3,
        "systems planning": 2, "proofs": 2,
        "hash map": 2, "intervals": 2, "graph BFS": 2, "sliding window": 2,
        "stack": 2, "data structure": 2, "system design": 2, "architecture": 2,
    }
    assert_no_eval_overlap(TRAIN_PROMPTS)
    for task in TRAIN_PROMPTS:
        assert task.split == "train"
        assert task.scoring_method in {
            "exact_match", "python_execution", "sql_execution", "llm_judge", "code_tests"
        }
        assert task.prompt and task.reference_response


@pytest.mark.parametrize("task", TRAIN_PROMPTS, ids=lambda task: task.prompt_id)
async def test_references_score_and_empty_answers_fail(task):
    reference_score = await score(task, task.reference_response, "dry-run", dry_run=True)
    assert reference_score >= (0.5 if task.scoring_method == "llm_judge" else 1.0)
    assert await score(task, "", "dry-run", dry_run=True) == 0.0


@pytest.mark.parametrize(
    "task", [t for t in TRAIN_PROMPTS if t.scoring_method.endswith("_execution")],
    ids=lambda task: task.prompt_id,
)
def test_execution_tasks_reject_eval_solution(task):
    eval_task = next(t for t in BENCHMARK_TASKS if t.scoring_method == task.scoring_method)
    assert score_task(task, eval_task.canned_responses["frontier"]) == 0.0
    assert score_task(eval_task, task.reference_response) == 0.0


@pytest.mark.parametrize("task", [t for t in TRAIN_PROMPTS if t.scoring_method == "sql_execution"])
def test_sql_fixtures_preserve_read_only_restriction(task):
    assert score_task(task, "DELETE FROM employees;") == 0.0
    assert score_task(task, "SELECT load_extension('unsafe');") == 0.0


@pytest.mark.parametrize("task", [t for t in TRAIN_PROMPTS if t.scoring_method == "python_execution"])
def test_python_fixtures_preserve_constrained_language(task):
    assert score_task(task, "import os\n" + task.reference_response) == 0.0


@pytest.mark.parametrize("method", ["python_execution", "sql_execution"])
def test_empty_fixture_sets_cannot_pass_vacuously(method):
    from dataclasses import replace

    task = next(t for t in TRAIN_PROMPTS if t.scoring_method == method)
    with pytest.raises(ValueError, match="at least one fixture"):
        score_task(replace(task, execution_fixtures=()), task.reference_response)
