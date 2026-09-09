"""Evidence-based routing over the configured NRP model ladder.

The router embeds an incoming request, fetches each configured model's nearest
scored historical neighbors, and selects the cheapest context-capable rung
with enough evidence that its mean observed effectiveness clears the current
session's bar.

Error contract: ``classify()`` deliberately propagates embedding and database
errors. The gateway layer owns classifier-failure handling; hiding failures
here would bypass that state machine.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from gatoway.embeddings import embed
from gatoway.providers import MODEL_LADDER, RUNG_NAMES

CONFIDENCE_FLOOR = 0.3
DEFAULT_THRESHOLD = 0.5
THRESHOLD_SHIFT_SCALE = 0.5

NEIGHBORS_PER_MODEL = 5
EFFECTIVENESS_BAR = 0.7
MIN_OBSERVATIONS = 2

# A known-cost, mid-ladder model replaces the historical "medium/Sonnet"
# default. Oversized requests use the cheapest rung that can hold them.
FALLBACK_RUNG = "gpt-oss"

# Compatibility exports for code that still calls a ladder position a tier.
TIERS = RUNG_NAMES
FALLBACK_TIER = FALLBACK_RUNG


class RequestTooLargeError(ValueError):
    """No configured model has enough context for the estimated request."""


@dataclass(frozen=True)
class NeighborObservation:
    routing_id: object | None
    model_id: str
    effectiveness: float | None
    difficulty: float | None
    similarity: float


@dataclass
class RoutingDecision:
    tier: str
    confidence: float
    low_confidence: bool
    calculated_difficulty: float | None
    matched_routing_id: object | None
    input_embedding: list[float]
    effectiveness_bar: float = EFFECTIVENESS_BAR
    observation_count: int = 0


def estimate_tokens(text: str) -> int:
    """Cheap context guard using the design's four-characters/token estimate."""
    return max(1, math.ceil(len(text) / 4))


def _value(row: Mapping[str, Any] | Any, key: str) -> Any:
    return row[key]


def _as_observation(row: Mapping[str, Any] | Any) -> NeighborObservation:
    return NeighborObservation(
        routing_id=_value(row, "routing_id"),
        model_id=_value(row, "model_id"),
        effectiveness=_value(row, "calculated_effectiveness"),
        difficulty=_value(row, "calculated_difficulty"),
        similarity=float(_value(row, "similarity")),
    )


def _model_rung_names() -> dict[str, str]:
    # Primaries define a model's rung. Add fallbacks only when that model is
    # not itself a primary (notably gemma, which shares qwen3-small's band).
    result = {rung.primary: rung.name for rung in MODEL_LADDER}
    for rung in MODEL_LADDER:
        for model in rung.models:
            result.setdefault(model, rung.name)
    return result


MODEL_RUNG_NAMES = _model_rung_names()
ROUTABLE_MODEL_IDS = tuple(MODEL_RUNG_NAMES)


def _context_capable_rungs(input_tokens: int) -> tuple[str, ...]:
    return tuple(
        rung.name for rung in MODEL_LADDER if rung.context_tokens >= input_tokens
    )


def fallback_rung_for_tokens(input_tokens: int) -> str:
    """Return the normal fallback, or the cheapest rung that fits the input."""
    capable = _context_capable_rungs(input_tokens)
    if not capable:
        largest_window = max(rung.context_tokens for rung in MODEL_LADDER)
        raise RequestTooLargeError(
            f"estimated input is {input_tokens:,} tokens; largest configured "
            f"context window is {largest_window:,}"
        )
    if FALLBACK_RUNG in capable:
        return FALLBACK_RUNG
    return capable[0]


def _routing_decision(
    rung_name: str,
    observations: Sequence[NeighborObservation],
    input_embedding: list[float],
    bar: float,
    low_confidence: bool,
) -> RoutingDecision:
    matched = max(observations, key=lambda item: item.similarity) if observations else None
    return RoutingDecision(
        tier=rung_name,
        confidence=matched.similarity if matched else 0.0,
        low_confidence=low_confidence,
        calculated_difficulty=matched.difficulty if matched else None,
        matched_routing_id=matched.routing_id if matched else None,
        input_embedding=input_embedding,
        effectiveness_bar=bar,
        observation_count=len(observations),
    )


def decide(
    neighbors: Sequence[NeighborObservation | Mapping[str, Any]],
    input_embedding: list[float],
    input_tokens: int,
    current_threshold: float = DEFAULT_THRESHOLD,
) -> RoutingDecision:
    """Choose the cheapest evidenced rung from already-fetched neighbors."""
    observations = [
        item if isinstance(item, NeighborObservation) else _as_observation(item)
        for item in neighbors
    ]
    confident = [item for item in observations if item.similarity >= CONFIDENCE_FLOOR]
    bar = EFFECTIVENESS_BAR + (
        current_threshold - DEFAULT_THRESHOLD
    ) * THRESHOLD_SHIFT_SCALE

    if not confident:
        fallback = fallback_rung_for_tokens(input_tokens)
        # Retain the best weak match in metadata while making it explicit that
        # it did not influence the selected rung.
        best_weak = sorted(observations, key=lambda item: item.similarity, reverse=True)[:1]
        return _routing_decision(
            fallback, best_weak, input_embedding, bar, low_confidence=True
        )

    capable = set(_context_capable_rungs(input_tokens))
    if not capable:
        fallback_rung_for_tokens(input_tokens)  # raises the detailed error

    by_rung: dict[str, list[NeighborObservation]] = defaultdict(list)
    for observation in confident:
        rung_name = MODEL_RUNG_NAMES.get(observation.model_id)
        if rung_name is not None:
            by_rung[rung_name].append(observation)

    for rung in MODEL_LADDER:
        rung_observations = [
            item
            for item in by_rung.get(rung.name, [])
            if item.effectiveness is not None
        ]
        if (
            rung.name in capable
            and len(rung_observations) >= MIN_OBSERVATIONS
            and sum(item.effectiveness for item in rung_observations)
            / len(rung_observations)
            >= bar
        ):
            return _routing_decision(
                rung.name, rung_observations, input_embedding, bar, low_confidence=False
            )

    # A single nearby outcome (or several ineffective outcomes) is not enough
    # evidence to promote. Fall back explicitly until a rung clears the same
    # minimum-observation and effectiveness requirements used above.
    fallback = fallback_rung_for_tokens(input_tokens)
    fallback_observations = by_rung.get(fallback, [])
    metadata_observations = fallback_observations or sorted(
        confident, key=lambda item: item.similarity, reverse=True
    )[:1]
    return _routing_decision(
        fallback, metadata_observations, input_embedding, bar, low_confidence=True
    )


def approximate_rung(
    difficulty: float, current_threshold: float = DEFAULT_THRESHOLD
) -> str:
    """Offline-eval fallback when no observation bank is available.

    Production routing never calls this helper. It only keeps the standalone
    benchmark runnable without Postgres while covering the full rung order.
    """
    shift = (current_threshold - DEFAULT_THRESHOLD) * THRESHOLD_SHIFT_SCALE
    effective = max(0.0, min(1.0, difficulty + shift))
    index = min(int(effective * len(MODEL_LADDER)), len(MODEL_LADDER) - 1)
    return MODEL_LADDER[index].name


async def classify(
    text: str, pool, current_threshold: float = DEFAULT_THRESHOLD
) -> RoutingDecision:
    """Embed ``text``, fetch top-k scored neighbors/model, and decide."""
    vector = embed(text)
    rows = await pool.fetch(
        """
        WITH ranked AS (
            SELECT routing_id, model_id, calculated_effectiveness,
                   calculated_difficulty,
                   1 - (input_embedding <=> $1) AS similarity,
                   row_number() OVER (
                       PARTITION BY model_id
                       ORDER BY input_embedding <=> $1
                   ) AS model_neighbor_rank
            FROM decision_history
            WHERE input_embedding IS NOT NULL
              AND calculated_effectiveness IS NOT NULL
              AND model_id = ANY($3::text[])
        )
        SELECT routing_id, model_id, calculated_effectiveness,
               calculated_difficulty, similarity
        FROM ranked
        WHERE model_neighbor_rank <= $2
        ORDER BY similarity DESC
        """,
        vector,
        NEIGHBORS_PER_MODEL,
        ROUTABLE_MODEL_IDS,
    )
    return decide(rows, vector, estimate_tokens(text), current_threshold)
