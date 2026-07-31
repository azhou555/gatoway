"""Eval Harness (SPEC.md §8), the "budget-vs-quality tradeoff report" demo
artifact.

Runs a small hand-written, held-out benchmark suite (eval split -- never
written back to decision_history, see gatoway/batch_job.py) through two
paths:
    1. The router: decide() picks a tier per task, that tier's provider is
       called.
    2. An "always frontier" baseline: every task goes to the frontier tier.

...then reports cost (sum of cost_cents) and effectiveness (per-task score,
exact_match or an llm_judge stub -- see BenchmarkTask docstring) for both,
and the headline cost-reduction / effectiveness-delta numbers.

Runs standalone: it does NOT require the FastAPI gateway (gatoway/app.py) to
be up. It talks to gatoway.router / gatoway.providers in-process.

Modes:
    --dry-run   Use canned per-tier responses instead of calling litellm.
                Auto-selected if neither ANTHROPIC_API_KEY nor
                OPENAI_API_KEY is set in the environment (with a printed
                notice -- never silently guessed).
    (default)   Call real providers via gatoway.providers.call_provider().

The router tier decision itself prefers a real DB round-trip
(gatoway.router.classify() against the seeded decision_history bank, see
gatoway/seed.py) but degrades gracefully to a standalone approximation
(gatoway.router.decide() using the task's own difficulty label as a stand-in
for a confident nearest-neighbor match) if Postgres isn't reachable, so this
harness never hard-depends on a live DB either.

Usage:
    python -m gatoway.eval
    python -m gatoway.eval --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from gatoway.providers import ProviderResponse, TIER_MODELS, call_provider
from gatoway.router import DEFAULT_THRESHOLD, decide

REPORT_PATH = Path(__file__).resolve().parent.parent / "eval_report.md"

# --- Dry-run cost proxy: parameter count, not invented cents --------------
#
# --dry-run makes no real provider call, so there's no real cost_cents to
# read off a litellm response. Rather than hand-picking fake cents per tier,
# use each tier's configured model's parameter count (billions) as the cost
# proxy -- bigger model ~ more compute ~ roughly more expensive, and it's a
# number we can actually source instead of making up.
#
# For local Ollama models this is queried for real from the running Ollama
# server (ollama exposes exact parameter_size per model). For hosted models
# whose parameter counts aren't publicly disclosed (Anthropic doesn't
# publish them for Haiku/Sonnet/Opus), fall back to rough, clearly-labeled
# order-of-magnitude estimates -- only the relative ordering matters for the
# demo story, not the exact figure.
PARAM_COUNT_B_ESTIMATE = {
    "cheap": 20.0,     # order-of-magnitude guess, not officially disclosed
    "medium": 200.0,   # order-of-magnitude guess, not officially disclosed
    "frontier": 2000.0,  # order-of-magnitude guess, not officially disclosed
}

_param_count_cache: dict[str, float] = {}


def _ollama_param_count_b(model_tag: str) -> float | None:
    """Query a locally running Ollama server for a model's real parameter
    count (billions). Returns None if Ollama isn't reachable or the model
    isn't pulled -- caller falls back to the estimate table.
    """
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/show",
            data=json.dumps({"name": model_tag}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.load(resp)
        size = data.get("details", {}).get("parameter_size", "")
        return float(size.rstrip("BbMm")) if size else None
    except Exception:
        return None


def param_count_b(tier: str) -> float:
    """Cost proxy for `tier`: real parameter count if it's a local Ollama
    model, else the documented order-of-magnitude estimate.
    """
    if tier in _param_count_cache:
        return _param_count_cache[tier]

    model = TIER_MODELS[tier][0]
    value = None
    if model.startswith("ollama/"):
        value = _ollama_param_count_b(model.removeprefix("ollama/"))
    if value is None:
        value = PARAM_COUNT_B_ESTIMATE.get(tier, 0.0)

    _param_count_cache[tier] = value
    return value


@dataclass
class BenchmarkTask:
    task_id: str
    prompt: str
    scoring_method: str  # "exact_match" | "llm_judge"
    # exact_match: list of substrings that must ALL appear (case-insensitive)
    # llm_judge: list of keywords used by the length+keyword heuristic stub
    expected: list[str]
    # Hand-labeled difficulty (0-1), matching the difficulty bucket the task
    # was designed to exercise. Used only as the standalone-mode fallback
    # match when no DB is reachable (see module docstring).
    difficulty: float
    split: str = "eval"  # SPEC.md §8: eval split, never written back
    # Canned responses per tier for --dry-run mode, hand-authored to reflect
    # a plausible quality gradient: cheap tiers do fine on easy tasks but
    # give thinner/partially-wrong answers on hard ones; frontier is
    # consistently thorough. This is what makes the dry-run report tell a
    # non-degenerate story (not "everything scores identically").
    canned_responses: dict[str, str] = field(default_factory=dict)


BENCHMARK_TASKS: list[BenchmarkTask] = [
    BenchmarkTask(
        task_id="capital_france",
        prompt="What is the capital of France?",
        scoring_method="exact_match",
        expected=["paris"],
        difficulty=0.10,
        canned_responses={
            "cheap": "The capital of France is Paris.",
            "medium": "Paris is the capital of France.",
            "frontier": "The capital of France is Paris.",
        },
    ),
    BenchmarkTask(
        task_id="arithmetic",
        prompt="What is 23 * 17?",
        scoring_method="exact_match",
        expected=["391"],
        difficulty=0.15,
        canned_responses={
            "cheap": "23 * 17 = 391.",
            "medium": "23 * 17 = 391.",
            "frontier": "23 * 17 = 391.",
        },
    ),
    BenchmarkTask(
        task_id="unit_conversion",
        prompt="Convert 68 degrees Fahrenheit to Celsius, rounded to the nearest integer.",
        scoring_method="exact_match",
        expected=["20"],
        difficulty=0.20,
        canned_responses={
            "cheap": "68F is 20C.",
            "medium": "68 degrees Fahrenheit is 20 degrees Celsius.",
            "frontier": "Using (F-32) * 5/9: (68-32) * 5/9 = 20 degrees Celsius.",
        },
    ),
    BenchmarkTask(
        task_id="quadratic_roots",
        prompt="Solve x^2 - 5x + 6 = 0 for x.",
        scoring_method="exact_match",
        expected=["2", "3"],
        difficulty=0.30,
        canned_responses={
            "cheap": "x = 2 or x = 3.",
            "medium": "Factoring gives (x-2)(x-3)=0, so x = 2 or x = 3.",
            "frontier": "Factoring: x^2 - 5x + 6 = (x-2)(x-3) = 0, so x = 2 and x = 3.",
        },
    ),
    BenchmarkTask(
        task_id="code_fix",
        prompt="Fix the off-by-one bug in: for i in range(1, n): print(arr[i])",
        scoring_method="llm_judge",
        expected=["range(0", "index", "off-by-one"],
        difficulty=0.45,
        canned_responses={
            "cheap": "Try range(0, n-1) instead.",
            "medium": "Change it to `for i in range(0, n):` -- starting at 1 skips "
                      "index 0, an off-by-one error, and this fixes it.",
            "frontier": "The loop starts at 1, so index 0 is skipped -- a classic "
                        "off-by-one bug. Use `for i in range(0, n):` to cover every "
                        "valid index from 0 to n-1 without going out of bounds.",
        },
    ),
    BenchmarkTask(
        task_id="sql_query",
        prompt="Write a SQL query to find the second-highest salary from an employees table.",
        scoring_method="llm_judge",
        expected=["order by", "limit", "offset"],
        difficulty=0.50,
        canned_responses={
            "cheap": "SELECT MAX(salary) FROM employees;",
            "medium": "SELECT salary FROM employees ORDER BY salary DESC LIMIT 1 OFFSET 1;",
            "frontier": "SELECT DISTINCT salary FROM employees ORDER BY salary DESC "
                        "LIMIT 1 OFFSET 1; -- DISTINCT guards against duplicate top salaries.",
        },
    ),
    BenchmarkTask(
        task_id="multistep_planning",
        prompt="Plan a 3-step migration strategy to move a monolithic app to "
               "microservices, considering data consistency risks.",
        scoring_method="llm_judge",
        expected=["strangler", "data consistency", "rollback", "incremental"],
        difficulty=0.75,
        canned_responses={
            "cheap": "Split the app into services and move the data over.",
            "medium": "1) Extract one bounded context at a time. 2) Keep the "
                      "shared DB temporarily. 3) Cut over once stable.",
            "frontier": "1) Extract a bounded context behind a strangler-fig facade, "
                        "keeping the shared DB short-term for data consistency. "
                        "2) Introduce an outbox pattern for incremental, dual-write-safe "
                        "migration of that context's data. 3) Cut over to its own store "
                        "with a rollback plan and shadow traffic before full cutover.",
        },
    ),
    BenchmarkTask(
        task_id="hard_math_proof",
        prompt="Prove that the square root of 2 is irrational.",
        scoring_method="llm_judge",
        expected=["contradiction", "even", "odd", "irrational"],
        difficulty=0.85,
        canned_responses={
            "cheap": "sqrt(2) is irrational because it cannot be written as a fraction.",
            "medium": "Assume sqrt(2)=a/b in lowest terms; then a^2=2b^2 so a is even; "
                      "this leads to b also being even, a contradiction.",
            "frontier": "Assume for contradiction sqrt(2)=a/b in lowest terms. Then "
                        "a^2=2b^2, so a^2 is even, so a is even; write a=2k, giving "
                        "4k^2=2b^2 so b^2=2k^2, so b is even too -- contradicting that "
                        "a/b was in lowest terms. Hence sqrt(2) is irrational.",
        },
    ),
]


def score_exact_match(response: str, expected: list[str]) -> float:
    """1.0 if every required substring appears in the response (case-insensitive),
    else 0.0. Deliberately binary -- this is the pass/fail branch of SPEC.md §8's
    "exact-match / execution-based pass-fail" scoring.
    """
    lowered = response.lower()
    return 1.0 if all(term.lower() in lowered for term in expected) else 0.0


# --- llm_judge stub --------------------------------------------------------
#
# SPEC.md §8 calls for "LLM-judge / rubric scoring" on open-ended tasks. For
# this MVP we do NOT call a real judge model -- that's out of scope per the
# task brief. Instead this is a cheap heuristic stand-in: half the score
# comes from response length relative to a target (a proxy for "did it
# actually explain itself" vs a one-liner), half from how many of the task's
# pre-registered keywords showed up (a proxy for "did it cover the right
# concepts"). This is NOT a substitute for a real rubric-based judge -- swap
# this function out first if this harness graduates past a demo.
LLM_JUDGE_TARGET_LENGTH_CHARS = 220


def score_llm_judge_stub(response: str, keywords: list[str]) -> float:
    length_component = min(len(response) / LLM_JUDGE_TARGET_LENGTH_CHARS, 1.0)
    lowered = response.lower()
    if keywords:
        keyword_component = sum(1 for kw in keywords if kw.lower() in lowered) / len(keywords)
    else:
        keyword_component = 0.0
    return 0.5 * length_component + 0.5 * keyword_component


def score_task(task: BenchmarkTask, response_text: str) -> float:
    if task.scoring_method == "exact_match":
        return score_exact_match(response_text, task.expected)
    if task.scoring_method == "llm_judge":
        return score_llm_judge_stub(response_text, task.expected)
    raise ValueError(f"unknown scoring_method {task.scoring_method!r}")


async def _dry_run_provider(tier: str, task: BenchmarkTask) -> ProviderResponse:
    content = task.canned_responses.get(tier, task.canned_responses.get("frontier", ""))
    return ProviderResponse(
        content=content,
        model_id=f"dry-run/{tier}",
        input_tokens=0,
        output_tokens=0,
        cost_cents=param_count_b(tier),  # cost proxy in --dry-run: see module docstring above
        raw=None,
    )


async def _real_provider(tier: str, task: BenchmarkTask) -> ProviderResponse:
    model = TIER_MODELS[tier][0]
    return await call_provider(model, [{"role": "user", "content": task.prompt}])


async def pick_router_tier(task: BenchmarkTask, pool) -> str:
    """Route `task` through the real router when a DB is available, else
    fall back to a standalone approximation. See module docstring.
    """
    if pool is not None:
        try:
            from gatoway.router import classify

            decision = await classify(task.prompt, pool, DEFAULT_THRESHOLD)
            return decision.tier
        except Exception as exc:  # DB reachable at connect time but query failed, etc.
            print(f"  [warn] classify() failed for {task.task_id!r} ({exc}); "
                  f"falling back to standalone difficulty-based routing")

    # Standalone fallback: no DB, or classify() failed. Approximate what a
    # populated bank would return by treating this task's own hand-labeled
    # difficulty as a confident nearest-neighbor match.
    decision = decide(
        similarity=0.9,
        difficulty=task.difficulty,
        matched_routing_id=None,
        input_embedding=[],
        current_threshold=DEFAULT_THRESHOLD,
    )
    return decision.tier


@dataclass
class TaskResult:
    task_id: str
    tier: str
    cost_cents: float
    score: float


async def run_eval(dry_run: bool, pool) -> tuple[list[TaskResult], list[TaskResult]]:
    provider_fn = _dry_run_provider if dry_run else _real_provider

    router_results: list[TaskResult] = []
    baseline_results: list[TaskResult] = []

    for task in BENCHMARK_TASKS:
        router_tier = await pick_router_tier(task, pool)
        router_response = await provider_fn(router_tier, task)
        router_results.append(TaskResult(
            task_id=task.task_id,
            tier=router_tier,
            cost_cents=router_response.cost_cents,
            score=score_task(task, router_response.content),
        ))

        baseline_response = await provider_fn("frontier", task)
        baseline_results.append(TaskResult(
            task_id=task.task_id,
            tier="frontier",
            cost_cents=baseline_response.cost_cents,
            score=score_task(task, baseline_response.content),
        ))

    return router_results, baseline_results


def _pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator * 100


def build_report(
    router_results: list[TaskResult], baseline_results: list[TaskResult], dry_run: bool
) -> str:
    router_cost = sum(r.cost_cents for r in router_results)
    baseline_cost = sum(r.cost_cents for r in baseline_results)
    router_effectiveness = sum(r.score for r in router_results) / len(router_results)
    baseline_effectiveness = sum(r.score for r in baseline_results) / len(baseline_results)

    cost_reduction_pct = _pct(baseline_cost - router_cost, baseline_cost)
    effectiveness_delta_pts = (router_effectiveness - baseline_effectiveness) * 100

    # dry-run has no real currency figure -- report is honest about using a
    # parameter-count proxy instead (see param_count_b() above) rather than
    # implying these are real dollars/cents.
    cost_label = "Compute Proxy (B params)" if dry_run else "Cost (¢)"
    cost_word = "compute-proxy" if dry_run else "cost"
    fmt = "{:.1f}".format if dry_run else "{:.3f}".format

    lines = []
    lines.append("# Eval Report: Router vs Always-Frontier Baseline\n")
    if dry_run:
        lines.append(
            "_--dry-run: no real provider calls. Cost column is a parameter-count "
            "proxy (real figure for local Ollama tiers, order-of-magnitude estimate "
            "for hosted tiers whose param counts aren't publicly disclosed), not real spend._\n"
        )
    lines.append(
        f"**Headline: {cost_reduction_pct:.0f}% {cost_word} reduction, "
        f"{effectiveness_delta_pts:+.0f} point effectiveness delta vs always "
        f"routing to the frontier tier.**\n"
    )
    lines.append(f"| Task | Router Tier | Router {cost_label} | Router Score | "
                  f"Baseline {cost_label} | Baseline Score |")
    lines.append("|---|---|---|---|---|---|")
    for r, b in zip(router_results, baseline_results):
        lines.append(
            f"| {r.task_id} | {r.tier} | {fmt(r.cost_cents)} | {r.score:.2f} | "
            f"{fmt(b.cost_cents)} | {b.score:.2f} |"
        )
    lines.append("")
    lines.append(f"**Totals** — Router: {fmt(router_cost)}, "
                  f"{router_effectiveness * 100:.1f}% effective. "
                  f"Frontier baseline: {fmt(baseline_cost)}, "
                  f"{baseline_effectiveness * 100:.1f}% effective.")
    lines.append(
        f"\n-> **{cost_reduction_pct:.0f}% {cost_word} reduction, "
        f"{effectiveness_delta_pts:+.0f}% effectiveness delta.**"
    )
    return "\n".join(lines)


async def _try_get_pool():
    try:
        from gatoway.db import get_pool

        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        return pool
    except Exception as exc:
        print(f"[info] Postgres unavailable ({exc}); running eval in standalone mode "
              f"(router tier decisions approximated from task difficulty labels, "
              f"no decision_history lookups).")
        return None


async def _main(dry_run: bool) -> None:
    pool = await _try_get_pool()
    try:
        router_results, baseline_results = await run_eval(dry_run, pool)
    finally:
        if pool is not None:
            from gatoway.db import close_pool

            await close_pool()

    report = build_report(router_results, baseline_results, dry_run)
    print(report)
    REPORT_PATH.write_text(report + "\n")
    print(f"\n[info] Wrote report to {REPORT_PATH}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gatoway eval harness")
    parser.add_argument("--dry-run", action="store_true",
                         help="Use canned responses instead of calling real providers.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    dry_run = args.dry_run
    if not dry_run and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        print("[info] No ANTHROPIC_API_KEY or OPENAI_API_KEY set -- auto-falling back to --dry-run.")
        dry_run = True
    asyncio.run(_main(dry_run))
