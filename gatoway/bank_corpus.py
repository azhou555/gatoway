"""Train-split prompt corpus for bootstrapping the decision_history bank
(docs/plans/2026-09-24-bank-densification.md).

Every prompt written into the bank must stay clear of the eval split
(SPEC.md §7/§8): the router matches on input embeddings, so a seed prompt that
restates a BENCHMARK_TASKS prompt hands that task a near-1.0 similarity match
and the gate measures seeding instead of routing.
"""

from __future__ import annotations

import difflib

from gatoway.eval import BENCHMARK_TASKS

# ponytail: character-level ratio catches restatements, not paraphrases. An
# embedding-similarity check against the router's own threshold is the upgrade
# if a reworded leak ever slips through.
OVERLAP_RATIO_LIMIT = 0.85


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def eval_overlaps(prompts: list[str]) -> list[tuple[str, str, float]]:
    """(prompt, eval task_id, ratio) for every prompt that is an exact
    (normalized) copy of, or too similar to, an eval-split prompt."""
    hits = []
    for prompt in prompts:
        for task in BENCHMARK_TASKS:
            a, b = _normalize(prompt), _normalize(task.prompt)
            ratio = 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()
            if ratio >= OVERLAP_RATIO_LIMIT:
                hits.append((prompt, task.task_id, round(ratio, 3)))
    return hits


def assert_no_eval_overlap(prompts: list[str]) -> None:
    hits = eval_overlaps(prompts)
    assert not hits, "train prompts overlap the eval split:\n" + "\n".join(
        f"  {ratio:.2f}  {task_id}  <-  {prompt!r}" for prompt, task_id, ratio in hits
    )
