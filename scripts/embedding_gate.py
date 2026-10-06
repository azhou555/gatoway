"""Pre-bootstrap embedding gate (no inference, no DB).

Replicates production retrieval: cosine similarity (pgvector `<=>`), top-5
nearest TRAIN prompts per model (same set across rungs since one embedding per
prompt), strict floor 0.4. For strict routing to ever fire for a task it needs
>=3 train prompts in that top-5 at >=0.4. Leak check: max similarity of each
target to the NEW json_exact prompts must stay < 0.58 (probe worst-case).

Prints task_id/suite/count/max-sim only -- never holdout prompt text -- so new
prompts can be pruned without the author reading the holdout.
"""
import json
from pathlib import Path

import numpy as np

from gatoway.embeddings import embed
from gatoway.eval import benchmark_tasks
from gatoway.bank_corpus import TRAIN_PROMPTS

FLOOR, TOPK, NEED = 0.40, 5, 3  # CEIL is calibrated below from the bank itself

new = [t for t in TRAIN_PROMPTS if t.scoring_method == "json_exact"]
allp = list(TRAIN_PROMPTS)
new_ids = {t.prompt_id for t in new}


def cos(a, b):
    a, b = np.array(a), np.array(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


# --- instance-identity check (ids only; never prints holdout text) -----------
import re
from gatoway.breadth_tasks import load_cases

eval_answers = {c["task_id"]: c["answer"] for c in load_cases()}
holdout_answers = {}
hp = Path("benchmarks/breadth/policy_holdout.json")
if hp.exists():
    holdout_answers = {it["task_id"]: it["answer"] for it in json.loads(hp.read_text())}
all_answers = {**eval_answers, **holdout_answers}


def nums(obj):
    return set(re.findall(r"-?\d+", json.dumps(obj)))


print("=== instance-identity check (answer equality / full numeric overlap) ===")
twins = []
for t in new:
    tnums = nums(t.expected_json)
    for tid, ans in all_answers.items():
        if t.expected_json == ans:
            twins.append(f"  ANSWER-EQ: {t.prompt_id} == {tid}")
        # numeric-subset only vs HOLDOUT: eval prompts are visible and already
        # confirmed distinct instances, so shared ints there aren't leakage.
        elif tid in holdout_answers and tnums and tnums <= nums(ans) and len(tnums) >= 2:
            twins.append(f"  NUM-SUBSET: {t.prompt_id} nums {sorted(tnums)} ⊆ {tid}")
print("\n".join(twins) if twins else "  (clean)")
print()


print("embedding train prompts...")
train_vecs = {t.prompt_id: embed(t.prompt) for t in allp}

# targets: expanded eval (original/coding/structured/reasoning) + holdout
targets = [(t.task_id, t.suite, t.prompt) for t in benchmark_tasks("expanded")]
holdout = Path("benchmarks/breadth/policy_holdout.json")
if holdout.exists():
    targets += [(it["task_id"], "holdout", it["prompt"])
                for it in json.loads(holdout.read_text())]

# Calibrate the near-twin ceiling from the bank's own accepted precedent: the
# highest similarity any EXISTING train prompt has to an original/coding eval
# task is, by definition, "same family, different instance" that the bank already
# ships. New prompts should not exceed it against the HELD-OUT holdout.
old_ids = {t.prompt_id for t in allp} - new_ids
precedent = 0.0
for tid, suite, prompt in targets:
    if suite not in ("original", "coding"):
        continue
    tv = embed(prompt)
    precedent = max(precedent, max(cos(tv, train_vecs[o]) for o in old_ids))
CEIL = round(precedent, 3)
print(f"calibrated near-twin ceiling (bank precedent) = {CEIL}\n")

print(f"{len(new)} new / {len(allp)} train prompts; {len(targets)} targets\n")
print(f"{'task_id':28} {'suite':11} {'nbrs>=.4(top5)':>14} {'max_new':>8} {'flags'}")
print("-" * 78)

fails = []
for tid, suite, prompt in targets:
    tv = embed(prompt)
    sims = sorted(((cos(tv, train_vecs[t.prompt_id]), t.prompt_id) for t in allp),
                  reverse=True)
    top5 = sims[:TOPK]
    count = sum(1 for s, _ in top5 if s >= FLOOR)
    max_new = max((s for s, pid in sims if pid in new_ids), default=0.0)
    flags = []
    # STARVED is a hard check only for the eval families we densify; holdout
    # starvation is a RESULT (we must not steer on holdout), reported not failed.
    if suite in ("structured", "reasoning") and count < NEED:
        flags.append("STARVED")
    # LEAK (near-twin) is the negative check against the held-out holdout only;
    # 0.6-0.75 against structured/reasoning eval is the desired neighbor signal.
    if suite == "holdout" and max_new > CEIL:
        flags.append("LEAK")
    if flags:
        fails.append((tid, suite, count, max_new, flags))
    note = "(starved-ok)" if suite == "holdout" and count < NEED else ""
    print(f"{tid:28} {suite:11} {count:>14} {max_new:>8.3f} {','.join(flags)} {note}")

# regression preview: how many NEW prompts land in the top-5 >=0.4 set of each
# original/coding eval task (JSON arithmetic drifting near multiply_* etc.)
print("\nregression preview (new prompts entering original/coding neighbor sets):")
for tid, suite, prompt in targets:
    if suite not in ("original", "coding"):
        continue
    tv = embed(prompt)
    sims = sorted(((cos(tv, train_vecs[t.prompt_id]), t.prompt_id) for t in allp),
                  reverse=True)
    intruders = [pid for s, pid in sims[:TOPK] if s >= FLOOR and pid in new_ids]
    if intruders:
        print(f"  {tid} ({suite}): {intruders}")

print("\n" + ("GATE FAIL:" if fails else "GATE PASS"))
for tid, suite, count, mx, flags in fails:
    print(f"  {tid} [{suite}] count={count} max_new={mx:.3f} {flags}")
