"""Router / Classifier (SPEC.md §3, §4, §6).

Embeds an incoming request, finds the nearest neighbor in `decision_history`
via pgvector cosine similarity, and picks a tier ("cheap" / "medium" /
"frontier", per gatoway/providers.py's TIER_MODELS) based on the matched
historical difficulty — shifted by the session's live `current_threshold`.

Error contract (SPEC.md §5, "ClassifierFailed"):
    `classify()` does NOT catch exceptions from the embedding call or the DB
    query. Any failure (embedding error, DB timeout, connection error, etc.)
    propagates to the caller. The gateway/circuit-breaker layer is
    responsible for catching it and applying the documented fallback: route
    straight to the "medium" (Sonnet) tier, single request, no circuit
    breaker involvement. Do not add a try/except here that swallows errors
    and silently returns a default decision -- that would hide failures from
    the layer whose job is to handle them.
"""

from __future__ import annotations

from dataclasses import dataclass

from gatoway.embeddings import embed

# --- Constants (documented per SPEC.md §4 / §6 / TASKS.md) ----------------

# Below this nearest-neighbor cosine similarity, treat it as "no good match"
# (SPEC.md §4 note) and fall back to the medium tier, marking the decision
# low-confidence rather than trusting a weak match.
CONFIDENCE_FLOOR = 0.3

# Bucket cutoffs for calculated_difficulty (assumed to live in [0, 1], same
# scale as similarity/confidence) into the three provider tiers. Simplest
# reasonable rule per TASKS.md: two static cutoffs, no learned boundaries.
DIFFICULTY_CHEAP_MAX = 0.33   # difficulty <= this -> "cheap"
DIFFICULTY_MEDIUM_MAX = 0.66  # difficulty <= this -> "medium"; above -> "frontier"

# Default session threshold (matches sessions.current_threshold DEFAULT 0.5
# in schema.sql). Used as the baseline for the shift below.
DEFAULT_THRESHOLD = 0.5

# How strongly a session's current_threshold shifts the effective difficulty
# before bucketing. SPEC.md §6 point 3: "a higher current_threshold should
# pull in higher tiers". We add (current_threshold - DEFAULT_THRESHOLD),
# scaled by this factor, directly onto calculated_difficulty before
# comparing against the cutoffs above. E.g. current_threshold=0.9 (max
# shift observed in practice) adds (0.9-0.5)*THRESHOLD_SHIFT_SCALE = 0.4*0.5
# = 0.2 to the effective difficulty, which is enough to push a borderline
# "medium" match into "frontier". Kept as a single linear constant rather
# than a curve -- simplest thing that satisfies "raise current_threshold ->
# pull in higher tiers".
THRESHOLD_SHIFT_SCALE = 0.5

TIERS = ("cheap", "medium", "frontier")

# Tier used when confidence is below CONFIDENCE_FLOOR (SPEC.md §4 note: "no
# good match" -> route to Sonnet). Must match a key in
# gatoway.providers.TIER_MODELS.
FALLBACK_TIER = "medium"


@dataclass
class RoutingDecision:
    tier: str
    confidence: float          # top-match similarity, or 0.0 if no match at all
    low_confidence: bool       # True if confidence < CONFIDENCE_FLOOR (fallback used)
    calculated_difficulty: float | None  # nearest match's difficulty, if any
    matched_routing_id: object | None    # routing_id of nearest match, if any
    input_embedding: list[float]


def _bucket_tier(effective_difficulty: float) -> str:
    """Pure bucketing of a difficulty score into a tier name."""
    if effective_difficulty <= DIFFICULTY_CHEAP_MAX:
        return "cheap"
    if effective_difficulty <= DIFFICULTY_MEDIUM_MAX:
        return "medium"
    return "frontier"


def decide(
    similarity: float | None,
    difficulty: float | None,
    matched_routing_id: object | None,
    input_embedding: list[float],
    current_threshold: float = DEFAULT_THRESHOLD,
) -> RoutingDecision:
    """Pure decision logic given an already-fetched nearest-neighbor match.

    Split out from `classify()` so router logic is testable with fake
    in-memory data -- no DB or embedding model required.

    `similarity`/`difficulty`/`matched_routing_id` should be None when the
    bank had no rows at all (cold start), which is treated the same as a
    below-floor match: low confidence, fallback tier.
    """
    if similarity is None or similarity < CONFIDENCE_FLOOR:
        return RoutingDecision(
            tier=FALLBACK_TIER,
            confidence=similarity or 0.0,
            low_confidence=True,
            calculated_difficulty=difficulty,
            matched_routing_id=matched_routing_id,
            input_embedding=input_embedding,
        )

    shift = (current_threshold - DEFAULT_THRESHOLD) * THRESHOLD_SHIFT_SCALE
    effective_difficulty = max(0.0, min(1.0, (difficulty or 0.0) + shift))

    return RoutingDecision(
        tier=_bucket_tier(effective_difficulty),
        confidence=similarity,
        low_confidence=False,
        calculated_difficulty=difficulty,
        matched_routing_id=matched_routing_id,
        input_embedding=input_embedding,
    )


async def classify(text: str, pool, current_threshold: float = DEFAULT_THRESHOLD) -> RoutingDecision:
    """Embed `text`, find its nearest neighbor in decision_history, and
    return a tier decision. See module docstring for the error contract:
    exceptions propagate, they are not caught here.

    `pool` is an asyncpg.Pool-like object (gatoway.db.get_pool()) exposing
    `.fetchrow(query, *args)`.
    """
    vector = embed(text)

    row = await pool.fetchrow(
        """
        SELECT routing_id, calculated_difficulty,
               1 - (input_embedding <=> $1) AS similarity
        FROM decision_history
        WHERE input_embedding IS NOT NULL
        ORDER BY input_embedding <=> $1
        LIMIT 1
        """,
        vector,
    )

    if row is None:
        return decide(None, None, None, vector, current_threshold)

    return decide(
        similarity=row["similarity"],
        difficulty=row["calculated_difficulty"],
        matched_routing_id=row["routing_id"],
        input_embedding=vector,
        current_threshold=current_threshold,
    )
