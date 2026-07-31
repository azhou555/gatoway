"""Unit tests for gatoway/session.py.

Pure keyword/overlap/threshold functions are tested directly. SessionTracker
is tested against a tiny in-memory fake pool (no real Postgres) that mimics
the subset of the asyncpg.Pool interface it uses (execute/fetchrow).
"""

from __future__ import annotations

import pytest

from gatoway.session import (
    DEFAULT_EXPECTED_TURN_COUNT,
    DEFAULT_THRESHOLD,
    MAX_THRESHOLD,
    SessionTracker,
    compute_threshold,
    extract_keywords,
    is_same_session,
    keyword_overlap,
)


# --- pure function tests ------------------------------------------------

def test_extract_keywords_drops_stopwords_and_short_words():
    keywords = extract_keywords("How do I fix the bug in my parser for the config file?")
    assert "the" not in keywords
    assert "how" not in keywords
    for kw in keywords:
        assert len(kw) >= 3


def test_keyword_overlap_identical_sets_is_one():
    assert keyword_overlap(["parser", "bug", "config"], ["parser", "bug", "config"]) == 1.0


def test_keyword_overlap_disjoint_is_zero():
    assert keyword_overlap(["parser", "bug"], ["recipe", "cake"]) == 0.0


def test_keyword_overlap_empty_stored_is_zero():
    assert keyword_overlap([], ["anything"]) == 0.0


def test_is_same_session_true_on_high_overlap():
    stored = ["parser", "bug", "config", "yaml", "loader"]
    new = ["parser", "bug", "config", "loader"]  # 4/5 overlap
    assert is_same_session(stored, new) is True


def test_is_same_session_false_when_topic_drifts():
    stored = ["parser", "bug", "config", "yaml", "loader"]
    new = ["recipe", "cake", "oven", "flour"]  # 0 overlap
    assert is_same_session(stored, new) is False


def test_threshold_stays_default_under_expected_turn_count():
    assert compute_threshold(turn_count=3, expected_turn_count=5) == DEFAULT_THRESHOLD


def test_threshold_rises_as_turns_exceed_expected():
    low = compute_threshold(turn_count=5, expected_turn_count=5)
    mid = compute_threshold(turn_count=7, expected_turn_count=5)
    high = compute_threshold(turn_count=9, expected_turn_count=5)
    assert low == DEFAULT_THRESHOLD
    assert mid > low
    assert high > mid


def test_threshold_capped_at_max():
    assert compute_threshold(turn_count=1000, expected_turn_count=5) == MAX_THRESHOLD


def test_threshold_uses_hardcoded_default_when_expected_unknown():
    # No expected_turn_count known for this session -> falls back to
    # DEFAULT_EXPECTED_TURN_COUNT (documented MVP simplification).
    with_default = compute_threshold(turn_count=10, expected_turn_count=None)
    with_explicit = compute_threshold(turn_count=10, expected_turn_count=DEFAULT_EXPECTED_TURN_COUNT)
    assert with_default == with_explicit


# --- SessionTracker tests against a fake pool ---------------------------

class FakePool:
    """Minimal in-memory stand-in for asyncpg.Pool, just enough for
    SessionTracker's two queries."""

    def __init__(self):
        self.sessions: dict[object, dict] = {}

    async def execute(self, query: str, *args):
        if "INSERT INTO sessions" in query:
            session_id, team_id, keywords, threshold = args
            self.sessions[session_id] = {
                "task_keywords": keywords,
                "turn_count": 1,
                "expected_turn_count": None,
                "current_threshold": threshold,
            }
        elif "UPDATE sessions" in query:
            session_id, turn_count, threshold, keywords = args
            self.sessions[session_id]["turn_count"] = turn_count
            self.sessions[session_id]["current_threshold"] = threshold
            self.sessions[session_id]["task_keywords"] = keywords

    async def fetchrow(self, query: str, session_id):
        row = self.sessions.get(session_id)
        return row


@pytest.mark.asyncio
async def test_start_session_stores_keywords_and_turn_one():
    pool = FakePool()
    tracker = SessionTracker(pool)
    result = await tracker.start_session("s1", "team1", "How do I debug this parser error?")
    assert result.turn_count == 1
    assert result.current_threshold == DEFAULT_THRESHOLD
    assert "parser" in result.task_keywords


@pytest.mark.asyncio
async def test_process_turn_same_topic_stays_same_session():
    pool = FakePool()
    tracker = SessionTracker(pool)
    await tracker.start_session("s1", "team1", "How do I debug this parser error in the config loader?")
    result = await tracker.process_turn("s1", "the parser config loader is still broken")
    assert result.same_session is True
    assert result.turn_count == 2


@pytest.mark.asyncio
async def test_process_turn_new_topic_flags_new_session():
    pool = FakePool()
    tracker = SessionTracker(pool)
    await tracker.start_session("s1", "team1", "How do I debug this parser error in the config loader?")
    result = await tracker.process_turn("s1", "What's a good recipe for chocolate cake?")
    assert result.same_session is False


@pytest.mark.asyncio
async def test_process_turn_raises_for_unknown_session():
    pool = FakePool()
    tracker = SessionTracker(pool)
    with pytest.raises(ValueError):
        await tracker.process_turn("does-not-exist", "hello")


@pytest.mark.asyncio
async def test_many_turns_raises_current_threshold():
    pool = FakePool()
    tracker = SessionTracker(pool)
    await tracker.start_session("s1", "team1", "debugging a parser config loader issue")
    result = None
    for _ in range(15):
        result = await tracker.process_turn("s1", "still stuck on the parser config loader issue")
    assert result.current_threshold > DEFAULT_THRESHOLD
