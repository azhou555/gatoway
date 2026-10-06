#!/usr/bin/env python3
"""Re-score an existing bank checkpoint offline, without re-running inference.

Editing any module hashed by ``bootstrap_bank.fingerprint`` (bank_corpus.py,
eval.py, ...) changes every task's fingerprint, so a plain ``bootstrap`` resume
would raise "checkpoint differs" on all existing rows and re-infer them. But the
raw model responses are already stored in each checkpoint
(``outcomes[model].response``). This script re-scores those stored responses
with the current scorer and refreshes the fingerprint, so a subsequent
``bootstrap --checkpoint <dst>`` skips every existing (prompt, model) -- zero
provider calls -- and only the newly added prompts cost NRP time.

Deterministic scorers (exact_match, json_exact, sql_execution) are re-run.
llm_judge and code_tests are NOT re-run by default (judge = a provider call;
code_tests = Docker); their stored score is preserved and the fingerprint still
refreshed. Pass --rescore-all to force those too (needs a judge key / Docker).

    .venv/bin/python scripts/rescore_bank.py --src artifacts/<db> --dst artifacts/<db2>

--dst defaults to --src (in place). Non-prompt files (summary, density, ...)
are left untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path

from gatoway.bank_corpus import TRAIN_PROMPTS, score
from gatoway.bootstrap_bank import fingerprint
from gatoway.code_grader import CodeGrader

OFFLINE_METHODS = {"exact_match", "json_exact", "sql_execution"}
BY_ID = {t.prompt_id: t for t in TRAIN_PROMPTS}


async def rescore(src: Path, dst: Path, rescore_all: bool) -> dict:
    if dst != src:
        dst.mkdir(parents=True, exist_ok=True)
    grader = CodeGrader()
    stats = {"prompts": 0, "rescored": 0, "preserved": 0, "missing_response": 0,
             "skipped_files": 0, "unknown_prompt": 0}

    for path in sorted(src.glob("*.json")):
        state = json.loads(path.read_text())
        task = BY_ID.get(state.get("prompt_id", "")) if isinstance(state, dict) else None
        if not isinstance(state, dict) or "outcomes" not in state or task is None:
            if dst != src:
                shutil.copyfile(path, dst / path.name)
            stats["skipped_files" if task is None else "unknown_prompt"] += 1
            continue

        stats["prompts"] += 1
        do_score = rescore_all or task.scoring_method in OFFLINE_METHODS
        for model, outcome in state["outcomes"].items():
            response = outcome.get("response")
            if response is None:
                stats["missing_response"] += 1
                continue
            if do_score:
                outcome["score"] = await score(task, response, model, grader=grader)
                stats["rescored"] += 1
            else:
                stats["preserved"] += 1
        # Refresh so a later bootstrap resume accepts the row as current.
        state["fingerprint"] = fingerprint(task)
        (dst / path.name).write_text(json.dumps(state, indent=2) + "\n")

    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--dst", type=Path)
    ap.add_argument("--rescore-all", action="store_true",
                    help="also re-run llm_judge (provider) and code_tests (Docker)")
    args = ap.parse_args()
    dst = args.dst or args.src
    stats = asyncio.run(rescore(args.src, dst, args.rescore_all))
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
