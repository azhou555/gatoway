"""Structure-dimension (D1 "both") report for the scaffold eval split.

Offline: runs the rubric `judge()` over the ALREADY-STORED scaffold responses in
a policy_eval run's outcomes.json and reports the structure score ALONGSIDE the
executable pass-rate. It does NOT touch routing or the bank signal — scaffold
tasks are graded executably (`code_tests`) for the bank; this is the separate
structure lens the executable grader can't see.

Judge is forced UNIFORM (glm-5 grades every cell) by passing
answer_model="openai/kimi" to judge(); verified no scaffold cell is glm-5 itself,
so glm-5 never grades its own output. This removes the cross-arm judge-leniency
confound (default judge selection differs by author model).

Scope: the 3 held-out eval scaffold tasks only (D1 makes the executable score the
bank signal; the 6 train-scaffold bank rows are judged by nothing that changes,
and their 2048-tok bootstrap truncations would be noise). Failures are recorded
as MISSING, never as a 0 score.

Usage: .venv/bin/python scripts/judge_scaffold.py [--run artifacts/policy_eval_p6]
"""
import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from gatoway.eval import benchmark_tasks
from gatoway.judge import judge, JudgeInfrastructureError

UNIFORM_JUDGE_ANSWER_MODEL = "openai/kimi"  # => judge() picks glm-5 for every cell


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="artifacts/policy_eval_p6")
    ap.add_argument("--out", default=None, help="results JSON (default: <run>/scaffold_structure.json)")
    args = ap.parse_args()

    run = Path(args.run)
    out = Path(args.out) if args.out else run / "scaffold_structure.json"
    outcomes = json.loads((run / "outcomes.json").read_text())

    tasks = {t.task_id: t for t in benchmark_tasks("scaffold")}
    for tid, t in tasks.items():
        if not getattr(t, "rubric", None):
            sys.exit(f"scaffold task {tid} has no rubric; cannot score structure")

    # scaffold cells: key "{run}/{task}/{model}" whose task is a scaffold eval task
    cells = {k: v for k, v in outcomes.items() if k.split("/")[1] in tasks}
    if not cells:
        sys.exit(f"no scaffold cells in {run}/outcomes.json")

    rows = []
    for key in sorted(cells):
        cell = cells[key]
        _, task_id, model = key.split("/")
        resp = cell["response"]
        row = {"key": key, "task": task_id, "model": model,
               "executable": cell.get("score"),
               "finish_reason": resp.get("finish_reason"),
               "judge_model": "openai/glm-5"}
        if resp.get("finish_reason") not in (None, "stop"):
            row.update(structure=None, status="skipped_incomplete")
        else:
            audit: list[dict] = []
            try:
                row["structure"] = await judge(
                    tasks[task_id].prompt, resp["content"], tasks[task_id].rubric,
                    UNIFORM_JUDGE_ANSWER_MODEL, audit=audit)
                row["criteria"] = audit[-1].get("criteria") if audit else None
                row["status"] = "ok"
            except JudgeInfrastructureError as exc:
                row.update(structure=None, status="missing", error=str(exc)[:200])
        rows.append(row)
        print(f"  {key:34s} exec={row['executable']!s:4} "
              f"struct={row['structure']!s:5} [{row['status']}]")

    # per (task, model) aggregate — executable and structure kept visibly separate
    agg = defaultdict(lambda: {"n": 0, "exec_sum": 0.0, "struct_sum": 0.0,
                               "struct_n": 0, "missing": 0})
    for r in rows:
        a = agg[(r["task"], r["model"])]
        a["n"] += 1
        a["exec_sum"] += r["executable"]
        if r["structure"] is None:
            a["missing"] += 1
        else:
            a["struct_sum"] += r["structure"]
            a["struct_n"] += 1

    print("\n  task          model     n  exec_mean  struct_mean  missing  judge")
    print("  " + "-" * 68)
    summary = []
    for (task, model), a in sorted(agg.items()):
        em = a["exec_sum"] / a["n"]
        sm = a["struct_sum"] / a["struct_n"] if a["struct_n"] else None
        summary.append({"task": task, "model": model, "n": a["n"],
                        "executable_mean": em, "structure_mean": sm,
                        "missing": a["missing"], "judge_model": "openai/glm-5"})
        print(f"  {task:13s} {model:8s} {a['n']:2d}   {em:7.3f}    "
              f"{('%.3f' % sm) if sm is not None else '  n/a':>7}    "
              f"{a['missing']:5d}    glm-5")

    out.write_text(json.dumps({"run": str(run), "uniform_judge": "openai/glm-5",
                               "rows": rows, "summary": summary}, indent=2))
    print(f"\n  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
