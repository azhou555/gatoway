from collections import Counter

import pytest

from gatoway.bank_corpus import TRAIN_PROMPTS, assert_no_eval_overlap, score
from gatoway.eval import BENCHMARK_TASKS, score_task

EXECUTION = ("python_execution", "sql_execution")


def test_prompt_ids_unique():
    ids = [p.prompt_id for p in TRAIN_PROMPTS]
    assert len(ids) == len(set(ids))


def test_every_neighborhood_can_meet_min_observations():
    counts = Counter(p.neighborhood for p in TRAIN_PROMPTS)
    assert min(counts.values()) >= 2, counts


def test_no_textual_overlap_with_eval_split():
    assert_no_eval_overlap([p.prompt for p in TRAIN_PROMPTS])


@pytest.mark.parametrize("prompt", TRAIN_PROMPTS, ids=lambda p: p.prompt_id)
def test_reference_answer_scores_full_marks(prompt):
    # Proves each prompt is answerable inside its scorer's constrained
    # language before any model call is spent on it.
    assert score(prompt, prompt.reference) == 1.0


@pytest.mark.parametrize(
    "prompt",
    [p for p in TRAIN_PROMPTS if p.scoring_method in EXECUTION],
    ids=lambda p: p.prompt_id,
)
def test_eval_answer_does_not_solve_train_prompt(prompt):
    # Semantic leakage the character guard cannot see: if the eval task's
    # correct answer also passes a train prompt, the two are the same task.
    for task in BENCHMARK_TASKS:
        if task.scoring_method != prompt.scoring_method:
            continue
        eval_answer = task.canned_responses["frontier"]
        assert score_task(task, eval_answer) == 1.0  # the reference is sound
        assert score(prompt, eval_answer) == 0.0, (prompt.prompt_id, task.task_id)
