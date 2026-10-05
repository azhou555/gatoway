"""Report measured evidence density using the production router's query."""

import argparse
import asyncio
from collections import defaultdict
import json
from pathlib import Path

from gatoway.bootstrap_bank import isolated_pool
from gatoway.embeddings import embed
from gatoway.eval import BENCHMARK_TASKS, EVAL_EXPECTED_TURN_COUNT, benchmark_tasks
from gatoway.providers import MODEL_LADDER
from gatoway.router import (
    CONFIDENCE_FLOOR, MIN_OBSERVATIONS, MODEL_RUNG_NAMES, EFFECTIVENESS_BAR,
    DEFAULT_THRESHOLD, THRESHOLD_SHIFT_SCALE, fetch_neighbors, decide, estimate_tokens,
)
from gatoway.session import compute_threshold


async def measure(pool, tasks=None):
    report = []
    turns = defaultdict(int)
    for task in (BENCHMARK_TASKS if tasks is None else tasks):
        turns[task.suite] += 1
        threshold = compute_threshold(turns[task.suite], EVAL_EXPECTED_TURN_COUNT)
        bar = EFFECTIVENESS_BAR + (threshold - DEFAULT_THRESHOLD) * THRESHOLD_SHIFT_SCALE
        vector = embed(task.prompt)
        rows = await fetch_neighbors(vector, pool)
        by_rung = defaultdict(list)
        for row in rows:
            if row["similarity"] >= CONFIDENCE_FLOOR and row["calculated_effectiveness"] is not None:
                by_rung[MODEL_RUNG_NAMES[row["model_id"]]].append(row)
        evidence = {
            rung.name: {
                "observations": len(by_rung[rung.name]),
                "mean_effectiveness": (
                    sum(row["calculated_effectiveness"] for row in by_rung[rung.name])
                    / len(by_rung[rung.name]) if by_rung[rung.name] else None),
                "similarities": [float(row["similarity"]) for row in by_rung[rung.name]],
            } for rung in MODEL_LADDER
        }
        dense = [name for name, stats in evidence.items()
                 if stats["observations"] >= MIN_OBSERVATIONS]
        clearing = [name for name in dense if evidence[name]["mean_effectiveness"] >= bar]
        decision = decide(rows, vector, estimate_tokens(task.prompt), threshold)
        report.append({
            "task_id": task.task_id, "suite": task.suite, "threshold": threshold,
            "effectiveness_bar": bar, "rungs_with_evidence": dense,
            "rungs_clearing_bar": clearing, "selected_rung": decision.tier,
            "low_confidence": decision.low_confidence, "evidence": evidence,
        })
    return report


def report_markdown(rows, bank_rows, database):
    dense = sum(len(row["rungs_with_evidence"]) >= 2 for row in rows)
    lines = [
        "# Measured bank density", "",
        f"Database: {database}. Bank rows: {bank_rows}.",
        f"{dense}/{len(rows)} tasks have at least two rungs with evidence.",
        "Evidence requires at least two scored observations with similarity >= 0.3.",
        "The effectiveness column applies the actual session-adjusted bar.", "",
        "| Suite | Task | Rungs with evidence | Rungs clearing effectiveness bar | Selected | Fallback |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(f'| {row["suite"]} | {row["task_id"]} | '
                     f'{len(row["rungs_with_evidence"])} | {len(row["rungs_clearing_bar"])} | '
                     f'{row["selected_rung"]} | {row["low_confidence"]} |')
    return "\n".join(lines) + "\n"


async def main(args):
    pool = await isolated_pool(args.database)
    try:
        count = await pool.fetchval("SELECT count(*) FROM decision_history")
        rows = await measure(pool, benchmark_tasks(args.suite))
    finally:
        await pool.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + "\n")
    markdown = report_markdown(rows, count, args.database)
    args.report.write_text(markdown)
    print(markdown)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--suite", choices=("legacy", "expanded"), default="legacy")
    parser.add_argument("--output", type=Path, default=Path("artifacts/bank_density.json"))
    parser.add_argument("--report", type=Path, default=Path("docs/bank_density.md"))
    asyncio.run(main(parser.parse_args()))
