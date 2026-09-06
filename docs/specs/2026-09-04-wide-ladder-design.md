# Design: Wide Model Ladder, Trustworthy Eval, and pgvector Task Decomposition

**Date:** 2026-09-04
**Status:** Implementation in progress — steps 1–3 complete; step 4 is next
**Supersedes parts of:** the architecture spec v0.1, `SPEC.md` today,
`docs/spec.md` after step 1 — see §3 below

---

## 1. Motivation

The gateway currently routes to three coarse tiers (`cheap` / `medium` /
`frontier`), a shape inherited from when those tiers were Haiku / Sonnet /
Opus. Now that every tier is an NRP-hosted open-weights model, the provider
menu is much wider — nine distinct working models spanning 12B to 1T
parameters — and three buckets throw most of that range away.

Two measurements taken during the NRP migration set the order of work, and
they invert the order the pivot was originally framed in:

**The scorer cannot support a wide ladder yet.** Across four back-to-back
eval runs, the four `exact_match` tasks scored 1.00 every single time,
while the four `llm_judge` tasks swung between 0.31 and 1.00 on the same
model and the same prompt. The judge is a length-and-keyword heuristic stub
that was tuned against short canned dry-run responses; it does not survive
verbose open-weights output. A scorer that cannot distinguish 0.31 from
0.60 under fixed conditions cannot distinguish a 27B rung from a 31B rung.

**The bank is too sparse to support a wide ladder yet.** `router.decide()`
buckets on the difficulty of a *single* nearest neighbor drawn from a 24-row
seed bank. Splitting that signal eight ways produces noise with more decimal
places, not finer routing.

Therefore the dependency order is:

```
scorer  →  bank density  →  ladder width  →  decomposition
```

Widening the ladder first would produce numbers that look more precise and
mean less.

### Credibility target

This is a **portfolio artifact**. The deliverable is a wide ladder plus an
eval whose numbers hold up to questioning. Decomposition ships behind a
measured cost gate and is allowed to ship as a negative result.

---

## 2. Non-goals

- Replacing the LLM-judge stub with a real LLM judge. Out of scope for the
  MVP per spec §8; the fix here is to move judge-scored tasks to
  execution-based scoring where the task admits it, and to report variance
  honestly where it does not.
- Escalation-based routing (try cheapest, verify, escalate). Considered and
  deferred — see §5.4.
- Streaming, multi-region, SSO/RBAC. Unchanged non-goals from spec §1.
- Switching to NRP's `qwen3-embedding`. Local `all-MiniLM-L6-v2` (384-dim)
  matches `schema.sql` and is free; switching means a migration plus a
  full re-seed for no measured benefit.

---

## 3. Documentation consolidation

Docs move under `docs/`:

| From | To |
|---|---|
| `SPEC.md` | `docs/spec.md` (bumped to v0.2) |
| `TASKS.md` | `docs/tasks.md` |
| `eval_report.md` | `docs/eval_report.md` (generated) |
| — | `docs/specs/2026-09-04-wide-ladder-design.md` (this file) |

`README.md` stays at the repo root by convention.

The roughly sixty `SPEC.md §N` references in module docstrings are left
alone: they name a section, not a path, and remain accurate. Only true path
references change — README links and `gatoway/eval.py:REPORT_PATH`.

### 3.1 Spec v0.1 → v0.2 deltas

Stale after the NRP migration:

- **§2 diagram and §3 table** — "Anthropic / OpenAI / OpenRouter / Ollama"
  becomes a single NRP OpenAI-compatible endpoint.
- **§5 state machine** — `UseMediumTier: default to Sonnet` names a model
  that is no longer reachable. Becomes a named mid-ladder fallback rung.
- **§4 notes** — "route to Sonnet" on low confidence, same fix.
- **§4 schema block** — still specifies `VECTOR(1536)` and still prescribes
  `CREATE INDEX ... USING ivfflat`, which `schema.sql` deliberately dropped
  with a written rationale (oversized `lists` on a small bank made
  `probes=1` miss the true nearest neighbor). **The spec contradicts the
  implementation, and the implementation is correct.** Spec follows code.
- **§10 open questions** — "pick embedding model" (resolved:
  all-MiniLM-L6-v2, 384 dims) and "define similarity-confidence floor"
  (resolved: 0.3) are both closed.

New in v0.2:

- §3 gains the model ladder in place of the three-tier table.
- §4 gains `decision_history.parent_routing_id` and `split`.
- §6 gains subtask routing and restates threshold shifting against the
  effectiveness bar rather than difficulty cutoffs.
- §8 gains execution-based scoring and session-level evaluation.

---

## 4. The ladder

### 4.1 Model inventory

NRP's `/v1/models` and the `/llms` documentation page disagree, and several
names alias one served model. Resolved by *served* model id, measured over 3
probe rounds on 2026-09-05 — full table, availability and latency in
`docs/nrp_characterization.md`:

| NRP name | Served id | Status |
|---|---|---|
| `gemma-small`, `gemma4-small`, `gemma4-12b` | `google/gemma-4-12B-it-qat-w4a16-ct` | one model, three aliases |
| `qwen3-small` | `Qwen/Qwen3.8-27B` | distinct |
| `gemma` | `google/gemma-4-31B-it-qat-w4a16-ct` | distinct |
| `gpt-oss` | `openai/gpt-oss-120b` | distinct |
| `qwen3` | `Qwen/Qwen3.8-Flash-Next-FP8` | distinct |
| `minimax-m2` | `MiniMaxAI/MiniMax-M2.7` | distinct |
| `deepseek-v4-flash` | `deepseek-ai/DeepSeek-V4-Flash-Vision-Exp` | distinct |
| `glm-5` | `Inferact/GLM-5.3-NVFP4` | distinct |
| `kimi` | `moonshotai/Kimi-K2.7-Code` | distinct |
| `gemma-small-e4b` | `google/gemma-4-E4B-it` | distinct |
| `qwen3-4bit` | — | no longer advertised |
| `qwen3-embedding` | — | not a chat model |

**Ten working distinct chat models**, all at 3/3 availability. Building a
ladder off the raw model list without deduplicating by served id would create
phantom rungs.

Two corrections from the characterization run. `gemma-small-e4b` failed a
single probe during the migration but returns 3/3 here — transient, and it is
now the fastest entry in the table, so it is reinstated. `qwen3-4bit` has left
NRP's inventory entirely (12 chat models are advertised, not 13); it is
excluded because it no longer exists, not because it failed.

### 4.2 Rungs

| Rung | Model | Params | Context |
|---|---|---|---|
| 0 | `gemma-small` | 12B | 262K |
| 1 | `qwen3-small` (fallback `gemma`) | 27B / 31B | 1M / 262K |
| 2 | `gpt-oss` | 120B | 131K |
| 3 | `qwen3` | 180B (6B active) | 1M |
| 4 | `minimax-m2` | 230B | 205K |
| 5 | `deepseek-v4-flash` | 304B | 1M |
| 6 | `glm-5` | 753B | 1M |
| 7 | `kimi` | 1T | 131K |
| — | `gemma-small-e4b` | ~4B (unconfirmed) | unconfirmed |

`gemma-small-e4b` is left **unnumbered** deliberately. It belongs below rung
0 on size, but inserting it would shift every index and §5.3 names "Rung 2
(`gpt-oss`, 120B)" by number. Its parameter figure is also the exact
total-versus-effective ambiguity §4.4 flags, and re-costing is design step 4's
job. Step 4 places it and confirms the figure.

27B and 31B share rung 1: they are not distinguishable as a cost band, so
`gemma` serves as rung 1's circuit-breaker fallback rather than its own rung.

Two decisions:

**Define all eight rungs and let the eval prune them.** Hand-picking which
rungs are "real" up front is a guess. A rung the bank never selects is
evidence, and removing it afterward is a defensible finding.

**Context window is a hard routing constraint, not a tie-breaker.** A
200K-token request cannot go to `gpt-oss` or `kimi` at any price. The router
filters by context before it considers cost. This matters more once
decomposition starts sizing subtasks.

### 4.3 Cost model

Unchanged from the NRP migration: NRP has no per-token billing and publishes
no price list, so `providers.MODEL_PARAMS_B` prices each model at its
published parameter count in billions per 1M tokens, flat across input and
output tokens. Only relative ordering is meaningful.

### 4.4 Risk: mixture-of-experts scrambles the ordering

`qwen3` is 180B total / 6B active. `kimi`, `glm-5`, `deepseek-v4-flash` and
`minimax-m2` are largely MoE as well, and NRP does not publish active-param
counts for most of them. Costing by total params (the published headline
figure) versus active params could reorder most of the ladder, not one
entry. Parameter counts alone cannot settle this.

**Mitigation attempted, and it did not work.** The characterization spike
recorded measured latency per rung (`docs/nrp_characterization.md`), and the
measurement does not discriminate: a 250x parameter range compresses into a
2x latency band, and `gemma` (31B, 511 ms) measures slower than `kimi` (1T,
505 ms). The probe generates 5 output tokens, so fixed request and scheduling
overhead dominates and model size barely enters. A probe measuring tokens/sec
over a longer generation could still produce the signal; more rounds of this
one cannot. **Until then params are the only evidence behind the cost model,
and this risk is open, not mitigated.**

The original reasoning, retained because the second signal is still the right
idea: the spike records *measured latency per rung* alongside params. Note this needs its own probe script,
**not** `gatoway/bench_latency.py`: that benchmark stubs the provider call
out to an instant stand-in on purpose, because spec §9 excludes provider
latency from the gateway's overhead budget. It measures the opposite of what
the ladder needs. Params remain the headline proxy because they
are published, stable and defensible.

---

## 5. Router

### 5.1 What is removed

`_bucket_tier()`, `DIFFICULTY_CHEAP_MAX`, `DIFFICULTY_MEDIUM_MAX` and the
`TIERS` triple all go away. `TIER_MODELS` collapses into the rung table plus
a per-rung fallback model.

This is the core argument for the redesign: `decision_history.model_id` is
already `TEXT` holding a concrete model, and `calculated_effectiveness` is
already recorded per row. **The schema already supports a per-model ladder.
The router is what is coarse**, discarding model identity at bucket time and
re-deriving it from two hardcoded cutoffs. Spec §1 claims the gateway routes
"rather than static per-request rules"; today it does not.

### 5.2 Selection algorithm

```
classify(text, pool, current_threshold):
    vector = embed(text)
    neighbors = k nearest rows by cosine similarity   # k = 5, was LIMIT 1
        -> (model_id, calculated_effectiveness, calculated_difficulty, similarity)

    confident = [n for n in neighbors if n.similarity >= CONFIDENCE_FLOOR]
    if not confident:
        return cold_start_decision()                  # §5.3

    bar = EFFECTIVENESS_BAR
        + (current_threshold - DEFAULT_THRESHOLD) * THRESHOLD_SHIFT_SCALE

    for model in ladder_ascending_by_cost:
        if context_window(model) < estimated_tokens(text):
            continue                                  # hard constraint
        observations = [n for n in confident if n.model_id == model]
        if len(observations) < MIN_OBSERVATIONS:
            continue                                  # no evidence, skip
        if mean(o.calculated_effectiveness for o in observations) >= bar:
            return decision(model, ...)

    return decision(highest_rung_seen(confident), ...)
```

Threshold shifting from spec §6 is preserved, relocated from the difficulty
side to the bar. A session that is struggling raises `current_threshold`,
which **raises the effectiveness bar**, which disqualifies cheaper models and
pulls in higher rungs. That is the same documented behavior — "a higher
`current_threshold` should pull in higher tiers" — expressed against the new
selection rule, and `THRESHOLD_SHIFT_SCALE` keeps its meaning.

`MIN_OBSERVATIONS` guards the sparse-bank problem directly: a model the bank
has no evidence for is never selected on the strength of zero rows.

`estimated_tokens()` is `len(text) / 4`, the standard rough
characters-per-token heuristic. It only has to be right to within an order
of magnitude, because it gates against context windows that differ by
roughly 8x between the smallest (131K) and largest (1M) rungs. It is
deliberately not a real tokenizer call: nine models across four families
would mean four tokenizers on the hot path, for a check that a crude
estimate already answers.

Starting constants, all tuned after step 3 (§10): `k = 5`,
`EFFECTIVENESS_BAR = 0.7`, `MIN_OBSERVATIONS = 2`. `CONFIDENCE_FLOOR` stays
at its current 0.3.

### 5.3 Cold start and sparse rungs

With eight rungs and a 24-row seed bank, most models start with zero
observations. Two consequences:

1. **`gatoway/seed.py` must cover the ladder.** Seed rows carry a
   `model_id`; seeding needs to spread across rungs so the router has
   evidence to select on. Seeding every rung evenly is not required —
   coverage of the rungs the eval actually exercises is.
2. **A named fallback rung replaces "default to Sonnet."** When no neighbor
   clears `CONFIDENCE_FLOOR`, the router returns the fallback rung and marks
   the decision low-confidence, exactly as today. Rung 2 (`gpt-oss`, 120B)
   is the proposed default: mid-ladder, non-MoE, so its cost position is not
   in doubt.

   The context constraint from §4.2 still applies to the fallback: `gpt-oss`
   holds 131K, the smallest window on the ladder, so a request too large for
   it falls back instead to the cheapest rung that *can* hold it. The
   fallback is a starting point in the ladder, not an exemption from it.

### 5.4 Considered and deferred: escalation routing

Start at the cheapest rung, verify the output, escalate on failure. Bounds
cost by budget and converges on frontier quality, and it would replace the
low-confidence guess with something principled.

Deferred because it needs a verifier — which is the scorer problem in a
different hat — and multiplies latency per request. Revisit only if
measurement shows the low-confidence fallback is costing real money.

---

## 6. Eval rework

This lands **before** the ladder widens. It is what makes a wide ladder
measurable.

### 6.1 Execution-based scoring

Spec §8 already specifies "exact-match / execution-based pass-fail for tasks
with a checkable answer (code that must pass tests, math with a numeric
answer)." `code_fix` and `sql_query` were previously judge-scored. This
change closes that gap:

- `code_fix` — run the returned code against assertions.
- `sql_query` — execute the query against a fixture table and compare
  result rows.

Both are deterministic, and both remove tasks from the heuristic that
produced all of the measured variance.

Implemented 2026-09-06: `code_fix` extracts and AST-validates a constrained
Python loop before running it against three array fixtures; `sql_query` runs
read-only candidates in an in-memory SQLite database against three salary
fixtures, including duplicate top salaries.

### 6.2 Honest reporting for what stays judged

`multistep_planning` and `hard_math_proof` remain judge-scored. They report
**mean and range across n runs**, never a single figure. The report already
carries a proxy-cost caveat; it gains a variance caveat.

Implemented 2026-09-06: the eval runs three repeated sessions and reports
per-task and session-level means and ranges.

### 6.3 Session-level evaluation

Spec §8 asks for effectiveness/cost "across a full simulated session (not
just single requests) — this is what demonstrates the min-maxing story."
The previous eval treated every task as an independent request.

Session-level evaluation is also the **only** thing that exercises
`current_threshold` shifting from spec §6, which the previous single-request
eval never touched at all.

Implemented 2026-09-06: the eight tasks run as consecutive turns with an
expected count of three. Turns 4–8 exercise increasing thresholds up to the
0.9 cap; the report records the threshold and selected tier for every turn.

### 6.4 Gate

**The six exact/execution-scored tasks must score identically across three
consecutive runs.** Passed on 2026-09-06 using live NRP calls and DB-backed
pgvector routing against an isolated 24-row seed bank: all six scored 1.00
in both paths in every run. The session result was a mean 40.1% proxy-cost
reduction (36.6–42.7% range) and a -1.0-point mean effectiveness delta
(-3.1 to 0.0) versus always-frontier.

---

## 7. Decomposition

### 7.1 Why it belongs to pgvector

A splitter call produces subtasks; each subtask routes through the
**existing** `classify()` path unchanged. Decomposition needs no new routing
machinery — a splitter in front, and parentage tracking behind.

The stronger argument is on the bank side. Whole tasks are heterogeneous
("build me a dashboard") and match their neighbors poorly, which is exactly
why nearest-neighbor over a small bank is weak. Subtasks are atomic ("write
a SQL query joining X and Y"), so they cluster tightly and match well. And
one decomposed task writes N rows where a whole task writes one.

**Decomposition densifies the bank and improves matching.** It attacks the
sparsity problem from §1 rather than depending on it being solved.

### 7.2 Cost gate

The splitter is itself an LLM call with real cost. Before decomposition is a
feature, it is a measurement:

> (splitter call + N subtask calls) vs. one frontier call,
> on **cost-per-passing-outcome**.

If it loses, it ships as a documented negative result. For a portfolio
artifact that is a legitimate outcome and better than a feature that
quietly does not pay for itself.

### 7.3 Eval-split leakage

Spec §7 and §8 are emphatic that eval runs never write back to the bank.
Decomposition breaks that guarantee unless parentage is tracked: decomposing
one held-out eval task would write N subtask rows into the bank the task is
supposed to be held out from, and every number afterward would be silently
wrong.

Closed in the same change: subtask rows carry `parent_routing_id` and
**inherit the parent's train/eval split label**, enforced in
`gatoway/batch_job.py` at write-back time.

### 7.4 Data model

```sql
ALTER TABLE decision_history
    ADD COLUMN parent_routing_id UUID REFERENCES decision_history(routing_id),
    ADD COLUMN split TEXT NOT NULL DEFAULT 'train';   -- 'train' | 'eval'
```

`split` makes the train/eval separation explicit in the schema rather than
implicit in which code path does the writing. `parent_routing_id` is NULL
for top-level requests.

---

## 8. Build order

| # | Step | Status | Gate |
|---|---|---|---|
| 1 | Docs consolidation + spec v0.2 | Complete | — (no code) |
| 2 | NRP characterization spike | Complete | rung table with latency + availability |
| 3 | Eval rework | Complete | **Passed: 3 identical execution-scored runs** |
| 4 | Wide ladder + router k-NN | Next | dead rungs pruned on evidence |
| 5 | Decomposition | Not started | **cost-per-passing-outcome beats one frontier call** |

Steps 3 and 5 are real gates. If step 3 does not stabilize, step 4 does not
start.

**Each step gets its own implementation plan.** This document is the design
for the pivot as a whole; it is deliberately too large to implement in one
pass. Steps 1 and 2 are mechanical and can share a plan. Steps 3, 4 and 5
each want their own, written against what the preceding gate actually
produced — writing step 4's plan before step 3's numbers exist would be
planning against assumptions this design exists to avoid.

### 8.1 What the characterization spike covers

Mostly done during the NRP migration; what remains:

- [x] Deduplicate by served model id — §4.1, ten distinct models
- [x] Availability across repeated probes — all 3/3. `gemma-small-e4b`'s
  failure was transient and it is reinstated; `qwen3-4bit` has left NRP's
  inventory entirely
- [x] Measured latency per rung, via `gatoway/characterize.py` — **measured,
  and it does not discriminate across the param range.** §4.4's mitigation is
  unproven, not validated; it needs a tokens/sec probe over a longer
  generation. Design step 4 must not treat the cost model as latency-checked
- [ ] Context window per rung — **not measured, carried forward.** The plan's
  prose said the probe would report it; the probe it specified does not, and
  NRP's `/v1/models` returns only `id`/`created`/`object`/`owned_by` — no
  `max_model_len` or `context_length`. §4.2 makes context a *hard* routing
  constraint, so a guessed figure would have the router accept requests a
  model cannot hold. `gemma-small-e4b`'s cell is `unconfirmed` for that
  reason. Source it from each model's upstream card before step 4 filters on
  it

---

## 9. Testing

- **Router selection** — pure-function tests against fake neighbor rows, as
  `decide()` is tested today. Cover: cheapest-clearing-bar wins; a model
  under `MIN_OBSERVATIONS` is skipped; a model whose context is too small is
  skipped; a raised `current_threshold` pulls in a higher rung; no confident
  neighbor returns the fallback rung marked low-confidence.
- **Ladder integrity** — every routable model is priced and reachable, rungs
  ascend by cost, each rung has a fallback. Extends `tests/test_providers.py`.
- **Split inheritance** — a subtask of an eval-split parent is never written
  back to the bank. This is the test that protects every downstream number.
- **Execution scorers** — a known-good and a known-bad answer per task, so a
  broken scorer fails rather than silently scoring everything 1.00.

---

## 10. Open questions

- Active-parameter counts for the MoE models are unpublished. Latency is the
  mitigation (§4.4), not a resolution.
- `k = 5`, `EFFECTIVENESS_BAR` and `MIN_OBSERVATIONS` are starting values,
  to be tuned once the eval is trustworthy — deliberately not tuned before
  step 3, since tuning against an unstable scorer is fitting to noise.
- Whether the splitter should itself be routed through the ladder, or pinned
  to a fixed rung. Pinned is the simpler starting answer; a splitter whose
  own cost varies makes the §7.2 gate harder to read.
