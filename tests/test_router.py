"""Unit coverage for evidence-based wide-ladder selection."""

from __future__ import annotations

from collections import Counter

import pytest

from gatoway.providers import RUNG_NAMES
from gatoway.router import (
    CONFIDENCE_FLOOR,
    DEFAULT_THRESHOLD,
    EFFECTIVENESS_BAR,
    FALLBACK_RUNG,
    MIN_OBSERVATIONS,
    NEIGHBORS_PER_MODEL,
    ROUTABLE_MODEL_IDS,
    NeighborObservation,
    RequestTooLargeError,
    approximate_rung,
    classify,
    decide,
    estimate_tokens,
)
from gatoway.seed import build_seed_rows

FAKE_EMBEDDING = [0.1, 0.2, 0.3]


def observation(model: str, effectiveness: float, similarity: float = 0.9, index: int = 1):
    return NeighborObservation(
        routing_id=f"id-{index}",
        model_id=f"openai/{model}",
        effectiveness=effectiveness,
        difficulty=0.5,
        similarity=similarity,
    )


def test_cheapest_rung_with_enough_effective_observations_wins():
    neighbors = [
        observation("gemma-small", 0.8, index=1),
        observation("gemma-small", 0.9, index=2),
        observation("qwen3-small", 0.95, index=3),
        observation("qwen3-small", 0.95, index=4),
    ]

    decision = decide(neighbors, FAKE_EMBEDDING, input_tokens=100)

    assert decision.tier == "gemma-small"
    assert decision.observation_count == MIN_OBSERVATIONS
    assert decision.effectiveness_bar == EFFECTIVENESS_BAR


def test_rung_under_minimum_observations_is_skipped():
    neighbors = [
        observation("gemma-small", 0.99),
        observation("qwen3-small", 0.8, index=2),
        observation("qwen3-small", 0.9, index=3),
    ]

    assert decide(neighbors, FAKE_EMBEDDING, 100).tier == "qwen3-small"


def test_shared_gemma_fallback_evidence_counts_for_qwen3_small_rung():
    neighbors = [
        observation("gemma", 0.8, index=1),
        observation("gemma", 0.9, index=2),
    ]

    assert decide(neighbors, FAKE_EMBEDDING, 100).tier == "qwen3-small"


def test_context_constraint_skips_a_cheaper_proven_rung():
    neighbors = [
        observation("gemma-small", 0.9, index=1),
        observation("gemma-small", 0.9, index=2),
        observation("qwen3-small", 0.9, index=3),
        observation("qwen3-small", 0.9, index=4),
    ]

    decision = decide(neighbors, FAKE_EMBEDDING, input_tokens=300_000)

    assert decision.tier == "qwen3-small"


def test_higher_session_threshold_raises_bar_and_promotes_rung():
    neighbors = [
        observation("gemma-small", 0.8, index=1),
        observation("gemma-small", 0.8, index=2),
        observation("qwen3-small", 0.95, index=3),
        observation("qwen3-small", 0.95, index=4),
    ]

    baseline = decide(neighbors, FAKE_EMBEDDING, 100, DEFAULT_THRESHOLD)
    shifted = decide(neighbors, FAKE_EMBEDDING, 100, 0.8)

    assert baseline.tier == "gemma-small"
    assert shifted.tier == "qwen3-small"
    assert shifted.effectiveness_bar > baseline.effectiveness_bar


def test_below_confidence_floor_uses_named_fallback():
    weak = [observation("gemma-small", 1.0, CONFIDENCE_FLOOR - 0.01)]

    decision = decide(weak, FAKE_EMBEDDING, 100)

    assert decision.tier == FALLBACK_RUNG
    assert decision.low_confidence is True
    assert decision.confidence == CONFIDENCE_FLOOR - 0.01


def test_empty_bank_uses_cheapest_context_capable_rung_for_large_input():
    decision = decide([], FAKE_EMBEDDING, input_tokens=300_000)

    assert decision.tier == "qwen3-small"
    assert decision.low_confidence is True


def test_request_larger_than_every_context_window_is_rejected():
    with pytest.raises(RequestTooLargeError, match="largest configured context"):
        decide([], FAKE_EMBEDDING, input_tokens=1_048_577)


def test_when_no_rung_clears_bar_explicit_fallback_wins():
    neighbors = [
        observation("gemma-small", 0.2, index=1),
        observation("gemma-small", 0.2, index=2),
        observation("kimi", 1.0, index=3),
    ]

    decision = decide(neighbors, FAKE_EMBEDDING, 100)

    assert decision.tier == FALLBACK_RUNG
    assert decision.low_confidence is True


def test_single_observation_cannot_promote_from_fallback():
    decision = decide(
        [observation("kimi", 1.0, index=1)], FAKE_EMBEDDING, input_tokens=100
    )

    assert decision.tier == FALLBACK_RUNG
    assert decision.low_confidence is True
    assert decision.observation_count == 1


def test_token_estimate_rounds_up_and_offline_approximation_spans_ladder():
    assert estimate_tokens("abcde") == 2
    assert approximate_rung(0.0) == "gemma-small"
    assert approximate_rung(1.0) == "kimi"


def test_cold_start_seed_has_three_observations_per_rung():
    counts = Counter(row["tier"] for row in build_seed_rows())

    assert tuple(counts) == RUNG_NAMES
    assert set(counts.values()) == {3}


@pytest.mark.asyncio
async def test_classify_fetches_top_k_with_model_outcomes(monkeypatch):
    from gatoway import router as router_module

    class Pool:
        async def fetch(self, query, vector, limit, model_ids):
            assert "model_id" in query
            assert "calculated_effectiveness" in query
            assert "PARTITION BY model_id" in query
            assert "calculated_effectiveness IS NOT NULL" in query
            assert "model_neighbor_rank <= $2" in query
            assert "model_id = ANY($3::text[])" in query
            assert limit == NEIGHBORS_PER_MODEL
            assert model_ids == ROUTABLE_MODEL_IDS
            assert vector == FAKE_EMBEDDING
            return [
                {
                    "routing_id": "one",
                    "model_id": "openai/gemma-small",
                    "calculated_effectiveness": 0.9,
                    "calculated_difficulty": 0.1,
                    "similarity": 0.9,
                },
                {
                    "routing_id": "two",
                    "model_id": "openai/gemma-small",
                    "calculated_effectiveness": 0.8,
                    "calculated_difficulty": 0.1,
                    "similarity": 0.8,
                },
            ]

    monkeypatch.setattr(router_module, "embed", lambda text: FAKE_EMBEDDING)
    decision = await classify("hello", Pool())

    assert decision.tier == "gemma-small"


@pytest.mark.asyncio
async def test_classify_propagates_embedding_errors(monkeypatch):
    from gatoway import router as router_module

    def boom(text: str):
        raise RuntimeError("embedding backend down")

    monkeypatch.setattr(router_module, "embed", boom)
    with pytest.raises(RuntimeError, match="embedding backend down"):
        await router_module.classify("hello", pool=None)
