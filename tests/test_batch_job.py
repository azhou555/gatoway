"""Unit tests for gatoway/batch_job.py.

Uses an in-memory FakePool (same pattern as tests/test_session.py) so these
run without a real Postgres connection. The critical property under test
(SPEC.md §7 point 2 / §8 "strict split, no leakage") is that
`close_session(..., is_train_split=False)` NEVER inserts into
decision_history -- proven directly by asserting on the fake pool's insert
log, not by inference from other behavior.
"""

from __future__ import annotations

import pytest

from gatoway.batch_job import (
    AVG_DIFFICULTY_EMA_ALPHA,
    close_session,
    compute_quality_score,
)
from gatoway.session import DEFAULT_EXPECTED_TURN_COUNT


# --- compute_quality_score -------------------------------------------------

def test_quality_score_at_expected_turn_count_is_perfect():
    session = {"turn_count": 5, "expected_turn_count": 5}
    assert compute_quality_score(session) == 1.0


def test_quality_score_double_expected_turns_is_zero():
    session = {"turn_count": 10, "expected_turn_count": 5}
    assert compute_quality_score(session) == 0.0


def test_quality_score_fewer_turns_than_expected_clamps_to_one():
    # Finishing early doesn't score above 1.0 -- clamped, not rewarded further.
    session = {"turn_count": 2, "expected_turn_count": 5}
    assert compute_quality_score(session) == 1.0


def test_quality_score_midpoint_is_half():
    session = {"turn_count": 7, "expected_turn_count": 5}  # ratio 1.4 -> 1 - 0.4 = 0.6
    assert compute_quality_score(session) == pytest.approx(0.6)


def test_quality_score_more_than_double_clamps_to_zero():
    session = {"turn_count": 50, "expected_turn_count": 5}
    assert compute_quality_score(session) == 0.0


def test_quality_score_missing_expected_turn_count_uses_default():
    session = {"turn_count": DEFAULT_EXPECTED_TURN_COUNT, "expected_turn_count": None}
    assert compute_quality_score(session) == 1.0


# --- close_session against a fake pool -------------------------------------

class FakePool:
    """Minimal in-memory stand-in for asyncpg.Pool covering the queries
    close_session() issues: sessions/decision_history/spend_ledger reads and
    writes.
    """

    def __init__(self, session_row=None, last_decision_row=None, ledger_row=None):
        self._session_row = session_row
        self._last_decision_row = last_decision_row
        self._ledger_row = ledger_row
        self.session_updates: list[tuple] = []
        self.decision_inserts: list[tuple] = []
        self.ledger_updates: list[tuple] = []

    async def fetchrow(self, query: str, *args):
        if "FROM sessions" in query:
            return self._session_row
        if "FROM decision_history" in query:
            return self._last_decision_row
        if "FROM spend_ledger" in query:
            return self._ledger_row
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def execute(self, query: str, *args):
        if "UPDATE sessions" in query:
            self.session_updates.append(args)
        elif "INSERT INTO decision_history" in query:
            self.decision_inserts.append(args)
        elif "UPDATE spend_ledger" in query:
            self.ledger_updates.append(args)
        else:
            raise AssertionError(f"unexpected execute query: {query}")


SESSION_ROW = {"team_id": "team1", "turn_count": 5, "expected_turn_count": 5}
LAST_DECISION_ROW = {
    "model_id": "anthropic/claude-sonnet-4-5",
    "calculated_difficulty": 0.5,
    "input_embedding": [0.1, 0.2],
    "response_embedding": [0.3, 0.4],
}
LEDGER_ROW = {"avg_session_difficulty": 0.4}


@pytest.mark.asyncio
async def test_close_session_writes_quality_score_regardless_of_split():
    pool = FakePool(session_row=SESSION_ROW, last_decision_row=LAST_DECISION_ROW, ledger_row=LEDGER_ROW)
    score = await close_session("s1", pool, is_train_split=False)
    assert score == 1.0
    assert len(pool.session_updates) == 1
    args = pool.session_updates[0]
    assert args[0] == "s1"
    assert args[1] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_close_session_train_split_writes_back_to_decision_history():
    pool = FakePool(session_row=SESSION_ROW, last_decision_row=LAST_DECISION_ROW, ledger_row=LEDGER_ROW)
    score = await close_session("s1", pool, is_train_split=True)

    assert len(pool.decision_inserts) == 1
    inserted = pool.decision_inserts[0]
    # (routing_id, session_id, model_id, calculated_difficulty,
    #  calculated_effectiveness, confidence, input_embedding, response_embedding)
    assert inserted[1] == "s1"
    assert inserted[2] == LAST_DECISION_ROW["model_id"]
    assert inserted[3] == LAST_DECISION_ROW["calculated_difficulty"]
    assert inserted[4] == pytest.approx(score)  # calculated_effectiveness == quality_score
    assert inserted[5] == 1.0  # full confidence: this is an observed outcome


@pytest.mark.asyncio
async def test_close_session_eval_split_does_not_write_back():
    """The critical strict-split guarantee (SPEC.md §7/§8): an eval-split
    session's outcome must never leak into decision_history.
    """
    pool = FakePool(session_row=SESSION_ROW, last_decision_row=LAST_DECISION_ROW, ledger_row=LEDGER_ROW)
    await close_session("s1", pool, is_train_split=False)
    assert pool.decision_inserts == []


@pytest.mark.asyncio
async def test_close_session_updates_avg_session_difficulty_via_ema():
    pool = FakePool(session_row=SESSION_ROW, last_decision_row=LAST_DECISION_ROW, ledger_row=LEDGER_ROW)
    await close_session("s1", pool, is_train_split=False)

    assert len(pool.ledger_updates) == 1
    team_id, new_avg = pool.ledger_updates[0]
    assert team_id == "team1"
    expected = LEDGER_ROW["avg_session_difficulty"] * (1 - AVG_DIFFICULTY_EMA_ALPHA) + \
        LAST_DECISION_ROW["calculated_difficulty"] * AVG_DIFFICULTY_EMA_ALPHA
    assert new_avg == pytest.approx(expected)


@pytest.mark.asyncio
async def test_close_session_first_ever_difficulty_sets_avg_directly():
    ledger_row = {"avg_session_difficulty": None}
    pool = FakePool(session_row=SESSION_ROW, last_decision_row=LAST_DECISION_ROW, ledger_row=ledger_row)
    await close_session("s1", pool, is_train_split=False)

    team_id, new_avg = pool.ledger_updates[0]
    assert new_avg == pytest.approx(LAST_DECISION_ROW["calculated_difficulty"])


@pytest.mark.asyncio
async def test_close_session_unknown_session_raises():
    pool = FakePool(session_row=None)
    with pytest.raises(ValueError):
        await close_session("does-not-exist", pool, is_train_split=False)


@pytest.mark.asyncio
async def test_close_session_no_decision_history_skips_writeback_and_ledger():
    # No routing decisions logged yet for this session -- nothing to write
    # back or use as a difficulty signal. Should not raise.
    pool = FakePool(session_row=SESSION_ROW, last_decision_row=None, ledger_row=LEDGER_ROW)
    score = await close_session("s1", pool, is_train_split=True)
    assert score == 1.0
    assert pool.decision_inserts == []
    assert pool.ledger_updates == []
