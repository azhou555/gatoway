"""Batch Feedback Job (SPEC.md §7), run at session end.

1. Compute `quality_score` for the session and write it to `sessions`.
2. If (and only if) this was a train-split session, write the session's
   representative embedding + outcome back into `decision_history` so the
   router's bank grows from real traffic. Eval-split sessions must NEVER be
   written back (SPEC.md §7 point 2 / §8 "strict split, no leakage") -- the
   `is_train_split` flag is the sole gate for this, and
   tests/test_batch_job.py asserts directly that an eval-split session
   produces no decision_history INSERT.
3. Update `spend_ledger.avg_session_difficulty` for the session's team.

MVP simplifications (documented, not hidden):
- The "representative embedding" for a session is just the input/response
  embedding of its most recent decision_history row, not a pooled/averaged
  embedding across the whole session. Good enough for an MVP demo; a real
  version might average or use the last-N turns.
- `avg_session_difficulty` is updated via a fixed-weight EMA
  (AVG_DIFFICULTY_EMA_ALPHA) rather than a true running mean, since
  spend_ledger doesn't track a session count to weight an exact average.
  Simplest thing that satisfies "running average is fine, don't
  over-engineer" per the task brief.
"""

from __future__ import annotations

import uuid

from gatoway.session import DEFAULT_EXPECTED_TURN_COUNT

# EMA weight applied to the *new* observation when updating
# spend_ledger.avg_session_difficulty. 0.3 means each session-close nudges
# the running average about 30% of the way toward the latest session's
# difficulty -- responsive without being a single-sample overwrite.
AVG_DIFFICULTY_EMA_ALPHA = 0.3


def compute_quality_score(session) -> float:
    """MVP heuristic quality score, per SPEC.md §7 point 1 and the task
    brief -- NOT an ML model.

    formula: clamp(1 - (turn_count - expected_turn_count) / expected_turn_count, 0, 1)

    Intuition: finishing in exactly `expected_turn_count` turns scores 1.0.
    Finishing in fewer turns also scores 1.0 (capped -- we don't reward
    "too fast" beyond perfect). Needing 2x the expected turns scores 0.0.
    Linear in between. This is an explicit proxy for "the router picked a
    tier good enough that the user didn't have to grind through many extra
    turns" -- not a measure of correctness or user sentiment (no such signal
    exists in the MVP's session data).

    `session` is any mapping-like object (dict or asyncpg.Record) exposing
    "turn_count" and "expected_turn_count".
    """
    turn_count = session["turn_count"] or 0
    expected = session["expected_turn_count"] or DEFAULT_EXPECTED_TURN_COUNT
    if expected <= 0:
        expected = DEFAULT_EXPECTED_TURN_COUNT

    raw = 1 - (turn_count - expected) / expected
    return max(0.0, min(1.0, raw))


async def close_session(session_id, pool, is_train_split: bool) -> float:
    """Run the end-of-session batch job for `session_id`. Returns the
    computed quality_score.

    `pool` is an asyncpg.Pool-like object exposing `.fetchrow()` / `.execute()`.
    """
    session = await pool.fetchrow(
        "SELECT team_id, turn_count, expected_turn_count FROM sessions WHERE session_id = $1",
        session_id,
    )
    if session is None:
        raise ValueError(f"unknown session_id {session_id!r}")

    quality_score = compute_quality_score(session)

    await pool.execute(
        "UPDATE sessions SET quality_score = $2, ended_at = now() WHERE session_id = $1",
        session_id,
        quality_score,
    )

    # Most recent routing decision in this session -- used as the session's
    # "representative" embedding/model/difficulty for write-back and for the
    # spend_ledger difficulty update. See module docstring's MVP note.
    last_decision = await pool.fetchrow(
        """
        SELECT model_id, calculated_difficulty, input_embedding, response_embedding
        FROM decision_history
        WHERE session_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        session_id,
    )

    if is_train_split and last_decision is not None:
        # input_embedding/response_embedding come back from the SELECT above
        # as pgvector's own text format ("[0.1,0.2,...]") -- asyncpg has no
        # registered codec for VECTOR columns on this pool (see
        # gatoway/seed.py's _to_pgvector docstring for the same gap), so it
        # falls back to returning/accepting the type as plain text. The
        # explicit ::vector cast here re-parses that same text on the way
        # back in.
        await pool.execute(
            """
            INSERT INTO decision_history
                (routing_id, session_id, model_id, calculated_difficulty,
                 calculated_effectiveness, confidence, input_embedding, response_embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8::vector)
            """,
            uuid.uuid4(),
            session_id,
            last_decision["model_id"],
            last_decision["calculated_difficulty"],
            quality_score,  # the real, now-known outcome -> calculated_effectiveness
            1.0,             # observed outcome, not a similarity match -> full confidence
            last_decision["input_embedding"],
            last_decision["response_embedding"],
        )

    if last_decision is not None and session["team_id"] is not None:
        difficulty = last_decision["calculated_difficulty"]
        if difficulty is not None:
            await _update_avg_session_difficulty(pool, session["team_id"], difficulty)

    return quality_score


async def _update_avg_session_difficulty(pool, team_id, difficulty: float) -> None:
    ledger = await pool.fetchrow(
        "SELECT avg_session_difficulty FROM spend_ledger WHERE team_id = $1", team_id
    )
    if ledger is None:
        return  # no ledger row for this team -- nothing to update (MVP: don't auto-create one)

    old_avg = ledger["avg_session_difficulty"]
    if old_avg is None:
        new_avg = difficulty
    else:
        new_avg = old_avg * (1 - AVG_DIFFICULTY_EMA_ALPHA) + difficulty * AVG_DIFFICULTY_EMA_ALPHA

    await pool.execute(
        "UPDATE spend_ledger SET avg_session_difficulty = $2, updated_at = now() WHERE team_id = $1",
        team_id,
        new_avg,
    )
