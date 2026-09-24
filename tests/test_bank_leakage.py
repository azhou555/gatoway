from gatoway import label_seed, seed
from gatoway.bank_corpus import assert_no_eval_overlap, eval_overlaps
from gatoway.eval import BENCHMARK_TASKS


def test_seed_prompts_do_not_leak_eval_split():
    prompts = [p for p, _, _ in seed.CHEAP_EXAMPLES + seed.MEDIUM_EXAMPLES + seed.FRONTIER_EXAMPLES]
    prompts += [p for _, p in label_seed.CANDIDATE_PROMPTS]
    assert_no_eval_overlap(prompts)


def test_guard_catches_verbatim_and_near_copies():
    # Guard against the guard going blind: case/whitespace variants and a
    # one-word edit of an eval prompt must both be flagged.
    verbatim = "  what IS the capital   of france? "
    one_word = BENCHMARK_TASKS[4].prompt.replace(" in:", ":")
    hits = {task_id for _, task_id, _ in eval_overlaps([verbatim, one_word])}
    assert hits == {"capital_france", "code_fix"}
