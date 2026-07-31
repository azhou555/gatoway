"""Unit tests for gatoway/router.py's pure decision logic.

Uses the `decide()` function directly with fake similarity/difficulty
values -- no real DB or embedding model involved, per TASKS.md's testing
guidance for Subtask 3.
"""

from __future__ import annotations

import pytest

from gatoway.router import (
    CONFIDENCE_FLOOR,
    DEFAULT_THRESHOLD,
    DIFFICULTY_CHEAP_MAX,
    DIFFICULTY_MEDIUM_MAX,
    FALLBACK_TIER,
    decide,
)

FAKE_EMBEDDING = [0.1, 0.2, 0.3]


def test_below_confidence_floor_triggers_fallback():
    decision = decide(
        similarity=CONFIDENCE_FLOOR - 0.01,
        difficulty=0.1,  # would otherwise bucket as "cheap"
        matched_routing_id="some-id",
        input_embedding=FAKE_EMBEDDING,
    )
    assert decision.low_confidence is True
    assert decision.tier == FALLBACK_TIER


def test_no_match_at_all_triggers_fallback():
    decision = decide(
        similarity=None,
        difficulty=None,
        matched_routing_id=None,
        input_embedding=FAKE_EMBEDDING,
    )
    assert decision.low_confidence is True
    assert decision.tier == FALLBACK_TIER
    assert decision.confidence == 0.0


def test_confidence_at_floor_is_not_low_confidence():
    # floor is inclusive on the "good" side: similarity == floor should pass.
    decision = decide(
        similarity=CONFIDENCE_FLOOR,
        difficulty=0.1,
        matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING,
    )
    assert decision.low_confidence is False


def test_tier_bucketing_cheap():
    decision = decide(
        similarity=0.9,
        difficulty=DIFFICULTY_CHEAP_MAX - 0.01,
        matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING,
    )
    assert decision.tier == "cheap"


def test_tier_bucketing_medium():
    decision = decide(
        similarity=0.9,
        difficulty=(DIFFICULTY_CHEAP_MAX + DIFFICULTY_MEDIUM_MAX) / 2,
        matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING,
    )
    assert decision.tier == "medium"


def test_tier_bucketing_frontier():
    decision = decide(
        similarity=0.9,
        difficulty=DIFFICULTY_MEDIUM_MAX + 0.01,
        matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING,
    )
    assert decision.tier == "frontier"


def test_higher_session_threshold_pulls_in_higher_tier():
    # A difficulty that buckets to "medium" at the default threshold should
    # be pulled up to "frontier" once current_threshold is raised enough
    # (SPEC.md §6 point 3).
    difficulty = DIFFICULTY_MEDIUM_MAX - 0.01

    baseline = decide(
        similarity=0.9,
        difficulty=difficulty,
        matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING,
        current_threshold=DEFAULT_THRESHOLD,
    )
    shifted = decide(
        similarity=0.9,
        difficulty=difficulty,
        matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING,
        current_threshold=0.9,
    )
    assert baseline.tier == "medium"
    assert shifted.tier == "frontier"


def test_higher_threshold_never_lowers_tier():
    # Sanity: shift is monotonic non-negative as current_threshold rises
    # above the default -- it should never *demote* a tier.
    difficulty = 0.1  # solidly "cheap"
    low = decide(
        similarity=0.9, difficulty=difficulty, matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING, current_threshold=DEFAULT_THRESHOLD,
    )
    high = decide(
        similarity=0.9, difficulty=difficulty, matched_routing_id="id",
        input_embedding=FAKE_EMBEDDING, current_threshold=0.8,
    )
    tier_rank = {"cheap": 0, "medium": 1, "frontier": 2}
    assert tier_rank[high.tier] >= tier_rank[low.tier]


@pytest.mark.asyncio
async def test_classify_propagates_embedding_errors():
    """SPEC.md §5 contract: classify() must not swallow exceptions -- the
    caller (circuit breaker layer) relies on this to trigger the
    classifier-failure fallback."""
    from gatoway import router as router_module

    def boom(text: str):
        raise RuntimeError("embedding backend down")

    router_module.embed = boom  # monkeypatch the module-level import
    try:
        with pytest.raises(RuntimeError, match="embedding backend down"):
            await router_module.classify("hello", pool=None)
    finally:
        from gatoway.embeddings import embed as real_embed

        router_module.embed = real_embed
