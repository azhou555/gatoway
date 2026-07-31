"""Seed script: writes a train-split bank of synthetic request/response pairs
into `decision_history` before any live traffic (SPEC.md §8 cold-start).

These rows exist purely so the router has *something* to match against on
day one -- without them every early request falls below CONFIDENCE_FLOOR and
gets routed to the fallback ("medium") tier regardless of actual difficulty
(see gatoway/router.py's decide()). No real LLM calls are made here: the
"response" text per example is hand-templated, just enough to embed and
produce a plausible response_embedding.

Each example is hand-labeled with a `calculated_difficulty` matching the
tier its prompt was designed to represent:
    - cheap:    0.05 - 0.30  (simple factual Q&A)
    - medium:   0.35 - 0.65  (moderate code fixes / short reasoning)
    - frontier: 0.70 - 0.95  (multi-step planning / hard math / proofs)

`calculated_effectiveness` is set high (0.85-0.98) for every seed row: these
are meant to represent "this tier handled this kind of request well",
establishing the initial cheap/medium/frontier clusters the real router will
match against. `confidence` is set to a fixed synthetic 0.95 (SEED_CONFIDENCE)
since there's no real nearest-neighbor match to report for a hand-authored
row -- it just marks these as high-trust seed data, not a live decision.

session_id is left NULL: `decision_history.session_id` is nullable
(no NOT NULL in schema.sql) and these rows aren't tied to any real session --
they're bank entries, not live traffic. routing_id is a fresh uuid4 per
insert, so re-running this script appends more seed rows rather than
upserting; safe to run once against a fresh DB per TASKS.md's cold-start use
case, but not idempotent (documented, not solved -- MVP).

Usage:
    python -m gatoway.seed
"""

from __future__ import annotations

import asyncio
import random
import uuid

from gatoway.db import close_pool, get_pool
from gatoway.embeddings import embed
from gatoway.providers import TIER_MODELS

SEED_CONFIDENCE = 0.95


def to_pgvector(values: list[float]) -> list[float]:
    """No-op passthrough: gatoway.db.get_pool() registers the pgvector
    asyncpg codec (see db.py's `_init_connection`), so a plain python list
    binds directly to a VECTOR column/parameter -- no text-format encoding
    or `::vector` cast needed. Kept as a named function (rather than
    removing the call sites) so seed.py and label_seed.py both go through
    one place if that ever changes again.
    """
    return values

# (prompt, canned "response" text, difficulty)
CHEAP_EXAMPLES: list[tuple[str, str, float]] = [
    ("What is the capital of France?", "The capital of France is Paris.", 0.08),
    ("What is the capital of Japan?", "The capital of Japan is Tokyo.", 0.08),
    ("Who wrote Romeo and Juliet?", "Romeo and Juliet was written by William Shakespeare.", 0.10),
    ("What is the boiling point of water in Celsius?", "Water boils at 100 degrees Celsius at sea level.", 0.10),
    ("What year did World War II end?", "World War II ended in 1945.", 0.10),
    ("What is 12 + 30?", "12 + 30 = 42.", 0.12),
    ("What is 7 times 8?", "7 times 8 is 56.", 0.12),
    ("How many continents are there?", "There are seven continents.", 0.14),
    ("What is the chemical symbol for gold?", "The chemical symbol for gold is Au.", 0.15),
    ("What is the largest planet in our solar system?", "Jupiter is the largest planet in our solar system.", 0.18),
]

MEDIUM_EXAMPLES: list[tuple[str, str, float]] = [
    (
        "Fix the off-by-one bug: for i in range(1, n): print(arr[i])",
        "Change the loop to `for i in range(0, n):` so index 0 is included and "
        "the last valid index n-1 is not skipped.",
        0.40,
    ),
    (
        "Write a Python function to check if a string is a palindrome.",
        "def is_palindrome(s):\n    s = s.lower().replace(' ', '')\n    return s == s[::-1]",
        0.42,
    ),
    (
        "Write a SQL query to find the second-highest salary from an employees table.",
        "SELECT MAX(salary) FROM employees WHERE salary < (SELECT MAX(salary) FROM employees);",
        0.45,
    ),
    (
        "Explain the difference between a list and a tuple in Python.",
        "Lists are mutable and defined with [], tuples are immutable and defined "
        "with (). Tuples are generally faster and hashable, so usable as dict keys.",
        0.48,
    ),
    (
        "Debug why this recursive Fibonacci function is slow for n=40.",
        "It's slow because it recomputes overlapping subproblems exponentially; "
        "add memoization (a dict cache) or switch to an iterative approach.",
        0.50,
    ),
    (
        "Summarize the tradeoffs between REST and GraphQL APIs.",
        "REST is simple and cacheable but can over/under-fetch; GraphQL lets "
        "clients request exactly the fields they need but adds server complexity.",
        0.55,
    ),
    (
        "Write a function to merge two sorted lists into one sorted list.",
        "def merge(a, b):\n    out = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n"
        "        if a[i] <= b[j]:\n            out.append(a[i]); i += 1\n"
        "        else:\n            out.append(b[j]); j += 1\n    return out + a[i:] + b[j:]",
        0.58,
    ),
    (
        "Explain why a database index speeds up reads but slows down writes.",
        "An index lets lookups skip straight to matching rows instead of "
        "scanning the table, but every insert/update/delete must also update "
        "the index structure, adding write overhead.",
        0.62,
    ),
]

FRONTIER_EXAMPLES: list[tuple[str, str, float]] = [
    (
        "Prove that the square root of 2 is irrational.",
        "Assume sqrt(2) = a/b in lowest terms. Then a^2 = 2b^2, so a^2 is even, "
        "so a is even; write a=2k, giving 4k^2=2b^2, so b^2=2k^2, so b is also "
        "even -- contradicting a/b being in lowest terms. Hence sqrt(2) is irrational.",
        0.78,
    ),
    (
        "Plan a 3-step migration strategy from a monolith to microservices, "
        "considering data consistency risks.",
        "1) Identify a bounded context and extract it behind a strangler-fig "
        "facade while keeping the shared DB temporarily. 2) Introduce an "
        "outbox/event log for cross-service writes to avoid dual-write "
        "inconsistency. 3) Cut the extracted service over to its own datastore "
        "with a rollback plan and dark-launch traffic shadowing before full cutover.",
        0.82,
    ),
    (
        "Design a rate limiter that supports both per-user and global limits "
        "with minimal lock contention.",
        "Use a sharded token-bucket: per-user buckets in local memory refilled "
        "on a timer, plus a global counter in Redis updated via a Lua script "
        "for atomicity; batch global-counter updates to reduce round trips.",
        0.85,
    ),
    (
        "Solve the recurrence T(n) = 2T(n/2) + n log n and give its asymptotic complexity.",
        "By the Akra-Bazzi/Master theorem extension for f(n)=n log n with a=2, "
        "b=2 (n^log_b(a) = n), since f(n) = n log n grows slightly faster than "
        "n by a log factor, T(n) = Theta(n log^2 n).",
        0.88,
    ),
    (
        "Design a distributed cache invalidation strategy for a multi-region "
        "deployment with eventual consistency requirements.",
        "Use versioned keys with a monotonic logical clock; propagate "
        "invalidations via a pub/sub log (e.g. Kafka) replicated cross-region, "
        "with a short TTL as a safety net against missed invalidation events "
        "and read-repair on version mismatch.",
        0.90,
    ),
    (
        "Given a directed graph with negative edge weights but no negative "
        "cycles, explain how to find shortest paths and why Dijkstra fails here.",
        "Dijkstra assumes a settled node's distance never improves, which "
        "negative edges violate; use Bellman-Ford (O(VE)) instead, which "
        "relaxes all edges V-1 times and can also detect negative cycles.",
        0.92,
    ),
]


def tier_for_difficulty(d: float) -> str:
    if d <= 0.33:
        return "cheap"
    if d <= 0.66:
        return "medium"
    return "frontier"


def build_seed_rows() -> list[dict]:
    """Pure helper (no DB/embedding calls) so the example bank composition
    is unit-testable if needed. Returns dicts without embeddings filled in.
    """
    rows = []
    for prompt, response, difficulty in CHEAP_EXAMPLES + MEDIUM_EXAMPLES + FRONTIER_EXAMPLES:
        tier = tier_for_difficulty(difficulty)
        rows.append(
            {
                "prompt": prompt,
                "response": response,
                "tier": tier,
                "difficulty": difficulty,
                "effectiveness": round(random.uniform(0.85, 0.98), 3),
            }
        )
    return rows


async def seed(pool) -> int:
    """Embed and insert all seed rows into decision_history. Returns count inserted."""
    rows = build_seed_rows()
    for row in rows:
        model_id = TIER_MODELS[row["tier"]][0]
        input_embedding = embed(row["prompt"])
        response_embedding = embed(row["response"])
        await pool.execute(
            """
            INSERT INTO decision_history
                (routing_id, session_id, model_id, calculated_difficulty,
                 calculated_effectiveness, confidence, input_embedding, response_embedding)
            VALUES ($1, NULL, $2, $3, $4, $5, $6, $7)
            """,
            uuid.uuid4(),
            model_id,
            row["difficulty"],
            row["effectiveness"],
            SEED_CONFIDENCE,
            to_pgvector(input_embedding),
            to_pgvector(response_embedding),
        )
    return len(rows)


async def _main() -> None:
    pool = await get_pool()
    try:
        count = await seed(pool)
        print(f"Seeded {count} synthetic decision_history rows "
              f"({len(CHEAP_EXAMPLES)} cheap, {len(MEDIUM_EXAMPLES)} medium, "
              f"{len(FRONTIER_EXAMPLES)} frontier).")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(_main())
