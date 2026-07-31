"""Session Tracker (SPEC.md §3, §6).

Naive, no-ML keyword extraction + overlap heuristic for session-boundary
detection, and a simple linear threshold-shift formula for
`sessions.current_threshold`. Deliberately dumb per TASKS.md's explicit MVP
cut ("TF-IDF/ML keyword extraction -> naive noun-phrase/keyword overlap
heuristic").

All DB-touching functions take an asyncpg.Pool-like `pool` (as returned by
gatoway.db.get_pool()) and operate on the `sessions` table. The
keyword/overlap/threshold math itself is split into plain pure functions so
it's unit-testable without a DB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Constants --------------------------------------------------------

# Small hardcoded stopword list -- not exhaustive, just enough to drop noise
# words that would otherwise dominate frequency counts. No NLTK/spaCy per
# TASKS.md MVP cut.
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of",
    "in", "on", "at", "for", "with", "about", "as", "by", "is", "are",
    "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "i", "you", "he", "she", "we", "they", "them", "my",
    "your", "his", "her", "our", "their", "me", "him", "us", "do", "does",
    "did", "can", "could", "will", "would", "should", "have", "has", "had",
    "not", "no", "yes", "please", "what", "how", "why", "when", "where",
    "which", "who", "there", "here", "from", "into", "up", "out", "just",
    "now", "get", "got",
}

TOP_N_KEYWORDS = 8

# Fraction of stored keywords that must reappear in a new turn's extracted
# keywords for it to still count as "same session". Below this, the "has
# the user moved on" heuristic fires and it's treated as a new session
# (SPEC.md §6 point 2).
SAME_SESSION_OVERLAP_FLOOR = 0.2

# MVP simplification (documented per TASKS.md): if a session doesn't carry
# an expected_turn_count from a benchmark difficulty label, assume this
# fixed default rather than computing a historical-cluster average.
DEFAULT_EXPECTED_TURN_COUNT = 5

DEFAULT_THRESHOLD = 0.5
# Cap so a very long session can't push current_threshold past this and
# force every remaining turn straight to "frontier".
MAX_THRESHOLD = 0.9
# Linear step per unit of turn_count/expected_turn_count ratio beyond 1.0.
# E.g. expected_turn_count=5, turn_count=10 -> ratio=2.0 -> shift =
# (2.0 - 1.0) * THRESHOLD_STEP = 0.4 -> current_threshold = 0.9 (capped).
# Simple linear function per SPEC.md §6 point 3 ("simple linear or step
# function... don't over-build").
THRESHOLD_STEP = 0.4


@dataclass
class TurnResult:
    same_session: bool
    turn_count: int
    current_threshold: float
    task_keywords: list[str]


def extract_keywords(text: str, top_n: int = TOP_N_KEYWORDS) -> list[str]:
    """Naive keyword extraction: lowercase, strip punctuation, drop
    stopwords/short tokens, then take the top-N words by (frequency, length)
    -- no TF-IDF, no ML, per TASKS.md.
    """
    words = re.findall(r"[a-z0-9']+", text.lower())
    counts: dict[str, int] = {}
    for w in words:
        if len(w) < 3 or w in STOPWORDS:
            continue
        counts[w] = counts.get(w, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    return [w for w, _ in ranked[:top_n]]


def keyword_overlap(stored: list[str], new: list[str]) -> float:
    """Fraction of `stored` keywords that also appear in `new`. 0.0 if
    `stored` is empty (nothing to overlap with -> treated as no overlap).
    """
    if not stored:
        return 0.0
    stored_set, new_set = set(stored), set(new)
    return len(stored_set & new_set) / len(stored_set)


def is_same_session(stored_keywords: list[str], new_keywords: list[str]) -> bool:
    """"Has the user moved on" heuristic: same session iff keyword overlap
    is at or above SAME_SESSION_OVERLAP_FLOOR.
    """
    return keyword_overlap(stored_keywords, new_keywords) >= SAME_SESSION_OVERLAP_FLOOR


def compute_threshold(turn_count: int, expected_turn_count: int | None) -> float:
    """Linear threshold shift (SPEC.md §6 point 3): once turn_count exceeds
    expected_turn_count, raise current_threshold proportionally to how far
    over it is, capped at MAX_THRESHOLD. At or under the expected count,
    threshold stays at the default.
    """
    expected = expected_turn_count or DEFAULT_EXPECTED_TURN_COUNT
    if expected <= 0:
        expected = DEFAULT_EXPECTED_TURN_COUNT
    ratio = turn_count / expected
    shift = max(0.0, (ratio - 1.0)) * THRESHOLD_STEP
    return min(MAX_THRESHOLD, DEFAULT_THRESHOLD + shift)


class SessionTracker:
    """Thin wrapper around the `sessions` table. Holds no state itself --
    every method reads/writes via `pool` so multiple gateway workers stay
    consistent (per TASKS.md: Postgres for session state in the MVP,
    swap to Redis later only if latency demands it).
    """

    def __init__(self, pool):
        self.pool = pool

    async def start_session(self, session_id, team_id, first_text: str) -> TurnResult:
        """First request in a session: extract keywords, initialize
        turn_count=1 and current_threshold=DEFAULT_THRESHOLD, insert the row.
        """
        keywords = extract_keywords(first_text)
        await self.pool.execute(
            """
            INSERT INTO sessions (session_id, team_id, task_keywords, turn_count, current_threshold)
            VALUES ($1, $2, $3, 1, $4)
            """,
            session_id, team_id, keywords, DEFAULT_THRESHOLD,
        )
        return TurnResult(
            same_session=True,
            turn_count=1,
            current_threshold=DEFAULT_THRESHOLD,
            task_keywords=keywords,
        )

    async def process_turn(self, session_id, text: str) -> TurnResult:
        """Subsequent request in a (possibly) existing session: check
        keyword overlap to decide same-vs-new session, bump turn_count,
        recompute current_threshold, and persist.
        """
        row = await self.pool.fetchrow(
            "SELECT task_keywords, turn_count, expected_turn_count FROM sessions WHERE session_id = $1",
            session_id,
        )
        if row is None:
            raise ValueError(f"unknown session_id {session_id!r}; call start_session first")

        stored_keywords = row["task_keywords"] or []
        new_keywords = extract_keywords(text)
        same = is_same_session(stored_keywords, new_keywords)

        turn_count = (row["turn_count"] or 0) + 1
        threshold = compute_threshold(turn_count, row["expected_turn_count"])
        # Keep accumulating keywords for the same session (union), otherwise
        # the boundary-detection heuristic starts a fresh keyword set.
        keywords = sorted(set(stored_keywords) | set(new_keywords)) if same else new_keywords

        await self.pool.execute(
            """
            UPDATE sessions
            SET turn_count = $2, current_threshold = $3, task_keywords = $4
            WHERE session_id = $1
            """,
            session_id, turn_count, threshold, keywords,
        )

        return TurnResult(
            same_session=same,
            turn_count=turn_count,
            current_threshold=threshold,
            task_keywords=keywords,
        )
