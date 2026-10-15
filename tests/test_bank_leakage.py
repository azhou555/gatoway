from types import SimpleNamespace

import pytest

from gatoway.bank_corpus import assert_no_eval_overlap
from gatoway.eval import BENCHMARK_TASKS
from gatoway.label_seed import CANDIDATE_PROMPTS
from gatoway.seed import CHEAP_EXAMPLES, MEDIUM_EXAMPLES, FRONTIER_EXAMPLES


@pytest.mark.parametrize(
    "prompt",
    [row[0] for row in CHEAP_EXAMPLES + MEDIUM_EXAMPLES + FRONTIER_EXAMPLES]
    + [prompt for _, prompt in CANDIDATE_PROMPTS],
)
def test_bank_sources_do_not_overlap_eval(prompt):
    assert_no_eval_overlap([prompt])


def test_guard_normalizes_case_and_whitespace_and_accepts_records():
    prompt = "  \n".join(BENCHMARK_TASKS[0].prompt.upper().split())
    with pytest.raises(AssertionError, match=r"exact match:.*capital_france.*ratio=1.000"):
        assert_no_eval_overlap([SimpleNamespace(prompt=prompt)])


def test_guard_reports_all_near_matches():
    prompts = [task.prompt + "!" for task in BENCHMARK_TASKS[:2]]
    with pytest.raises(AssertionError) as exc:
        assert_no_eval_overlap(iter(prompts))
    assert "capital_france" in str(exc.value)
    assert "arithmetic" in str(exc.value)
    assert "near match" in str(exc.value)
    assert "ratio=" in str(exc.value)


def test_guard_accepts_distinct_prompts():
    assert_no_eval_overlap(["Describe the lifecycle of a butterfly."])
    assert_no_eval_overlap([])
