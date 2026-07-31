"""Interactive seed-bank growth: you supply the difficulty label, no LLM
calls needed. Complements gatoway/seed.py's hand-labeled cold-start bank
with your own judgment on a broader set of realistic prompts, which is what
actually improves routing quality (SPEC.md §3's classifier is only as good
as its nearest-neighbor bank).

For each prompt below, type a difficulty 0.0 (trivial) - 1.0 (very hard).
Tier is derived automatically from that number (gatoway.seed.tier_for_difficulty,
same cutoffs the router itself buckets on). Each label is embedded and
inserted into decision_history immediately, so quitting early (Ctrl-C or 'q')
keeps everything labeled so far -- nothing is lost or held in a batch.

No response text is generated (there's no real model call here), so
response_embedding is left NULL -- classify() only reads input_embedding,
so this doesn't affect routing.

Usage:
    python -m gatoway.label_seed
"""

from __future__ import annotations

import asyncio
import uuid

from gatoway.db import close_pool, get_pool
from gatoway.embeddings import embed
from gatoway.providers import TIER_MODELS
from gatoway.seed import SEED_CONFIDENCE, tier_for_difficulty, to_pgvector

# (theme, prompt) -- themes are just for your context while labeling, not
# stored anywhere. Deliberately distinct from seed.py's existing 24 examples,
# to broaden bank coverage rather than duplicate it.
CANDIDATE_PROMPTS: list[tuple[str, str]] = [
    ("support", "How do I reset my account password?"),
    ("support", "Why was I charged twice for my subscription this month?"),
    ("support", "Walk me through migrating my account to a new email address without losing my data."),
    ("writing", "Write a one-sentence product tagline for a budgeting app."),
    ("writing", "Draft a short apology email to a customer whose order shipped a week late."),
    ("writing", "Write a short story about a lighthouse keeper who discovers a message in a bottle."),
    ("data", "Write a query to count orders per customer in the last 30 days."),
    ("data", "This dashboard shows a sudden 40% drop in signups yesterday -- what would you check first?"),
    ("data", "Design a schema for a multi-tenant SaaS app with per-tenant data isolation."),
    ("infra", "What does a 502 Bad Gateway error usually mean?"),
    ("infra", "Our API's p99 latency doubled after the last deploy but p50 is unchanged -- what's the likely cause?"),
    ("infra", "Design a zero-downtime schema migration plan for a table with 500M rows under constant write load."),
    ("business", "Summarize the pros and cons of a freemium vs. free-trial pricing model."),
    ("business", "We're deciding whether to build or buy a customer support ticketing system -- what factors matter most?"),
    ("science", "Why is the sky blue?"),
    ("science", "Explain how CRISPR gene editing works and its main off-target risk."),
    ("code", "What's the difference between `==` and `is` in Python?"),
    ("code", "Review this function for thread-safety issues: a counter incremented without a lock across worker threads."),
    ("agentic", "Given a failing CI pipeline with three unrelated test failures, plan how to triage and fix them one at a time."),
    ("agentic", "Design an incident response runbook for a payment processor outage, including rollback and customer comms steps."),
]


def _prompt_difficulty(i: int, total: int, theme: str, text: str) -> float | None:
    """Returns None for skip, raises SystemExit (via KeyboardInterrupt) on quit."""
    print(f"\n[{i}/{total}] ({theme})")
    print(f"  {text}")
    while True:
        raw = input("  difficulty 0.0-1.0 (or 's' skip, 'q' quit): ").strip().lower()
        if raw in ("q", "quit"):
            raise KeyboardInterrupt
        if raw in ("s", "skip", ""):
            return None
        try:
            value = float(raw)
        except ValueError:
            print("  not a number -- try again.")
            continue
        if not (0.0 <= value <= 1.0):
            print("  must be between 0.0 and 1.0 -- try again.")
            continue
        return value


async def _insert(pool, text: str, difficulty: float) -> str:
    tier = tier_for_difficulty(difficulty)
    model_id = TIER_MODELS[tier][0]
    input_embedding = embed(text)
    await pool.execute(
        """
        INSERT INTO decision_history
            (routing_id, session_id, model_id, calculated_difficulty,
             calculated_effectiveness, confidence, input_embedding)
        VALUES ($1, NULL, $2, $3, $4, $5, $6)
        """,
        uuid.uuid4(),
        model_id,
        difficulty,
        0.9,  # matches seed.py's convention: these represent "handled well at this tier"
        SEED_CONFIDENCE,
        to_pgvector(input_embedding),
    )
    return tier


async def main() -> None:
    pool = await get_pool()
    inserted = 0
    try:
        total = len(CANDIDATE_PROMPTS)
        for i, (theme, text) in enumerate(CANDIDATE_PROMPTS, start=1):
            try:
                difficulty = _prompt_difficulty(i, total, theme, text)
            except KeyboardInterrupt:
                print("\nStopping early -- everything labeled so far is already saved.")
                break
            if difficulty is None:
                continue
            tier = await _insert(pool, text, difficulty)
            inserted += 1
            print(f"  -> inserted as {tier} (difficulty={difficulty:.2f})")
    finally:
        print(f"\nDone: {inserted}/{len(CANDIDATE_PROMPTS)} labeled and inserted.")
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
