# Coding Task Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the bank and the gate reflect the traffic gatoway will actually
carry — coding agents. Add LeetCode-style Python and TypeScript problems graded
by hidden tests in Docker, and system-design / architecture prompts graded by a
real rubric-based LLM judge, to **both** the train corpus and the eval suite.

**Decisions (user, 2026-09-24):**
1. Coding tasks go into train *and* eval, so the gate measures coding routing.
   This breaks comparability with every recorded gate number; the next gate
   is reported as a new baseline, not a delta against the old one.
2. Code is graded by hidden tests inside the existing locked-down Docker
   sandbox (`agentic_eval.DockerGrader`'s flags), never on the host.
3. Design answers are graded by a real LLM judge against a per-prompt rubric.
   This reverses DESIGN.md's "Real LLM judge: rejected for MVP" row.

**Sequencing:** this plan slots between Task 2 and Task 3 of
`docs/plans/2026-09-24-bank-densification.md`. Densification Task 3 (bootstrap)
consumes the scorers built here; Task 4 (re-gate) runs the expanded eval.

**Tech Stack:** Python 3.13, pytest, Docker (`python:3.13-slim`,
`node:22-slim`), Node's built-in type stripping + `node:test` for TypeScript
(no `tsc`, no npm install), litellm against NRP.

---

## Global Constraints

- Everything in the densification plan's Global Constraints still applies.
- **Untrusted model code only ever runs in Docker.** The pytest suite runs our
  own *reference* solutions locally with `python`/`node` subprocesses — trusted
  code, so no sandbox — and skips TS checks when `node` is absent.
- Tests must not require Docker or network. The Docker path is covered by one
  opt-in integration test (`GATOWAY_DOCKER_TESTS=1`).
- Leakage: every new prompt passes `bank_corpus.assert_no_eval_overlap`, and
  the semantic cross-check extends to code: **each eval reference solution must
  fail every train task's hidden tests, and vice versa.**

---

### Task A: Code-test grader (Python + TypeScript)

**Files:** Create `gatoway/code_grader.py`, `tests/test_code_grader.py`.

**Task layout** — one directory per problem, same pattern as `benchmarks/agentic/`:

```
benchmarks/coding/{eval,train}/<task_id>/
  task.toml        # language, neighborhood, entrypoint (function name), difficulty (eval only)
  prompt.md        # includes the exact function signature to implement
  reference.py|ts  # known-good solution
  test_hidden.py|hidden.test.ts
```

- [x] Extract the answer: last fenced block tagged for the task's language
  (`python`/`py`, `typescript`/`ts`), else the last untagged block. Nothing
  found → score 0.0 without starting a container.
- [x] Write `solution.py`/`solution.ts` plus the hidden test into a temp dir;
  run it read-only in Docker with `DockerGrader`'s isolation flags.
  Python: `python -m unittest`. TS: `node --experimental-transform-types --test`
  (transform, not strip, so answers using `enum` still run — **verify the flag
  on `node:22-slim` first; fall back to `node:24-slim` if needed**).
- [x] Score = fraction of hidden test cases passed (parsed from the runner's
  summary), not binary: a 7/10 answer is evidence of a partially capable rung.
  Timeout or crash → 0.0. Docker unavailable → raise, never score (mirrors
  `AgenticInfrastructureError`: infra failure must not become a 0.0 row).
- [x] Refactor the shared `docker run` flags out of `agentic_eval.DockerGrader`
  into one function both graders call — no copy.
- [x] Unit tests with a fake runner: extraction picks the right block; missing
  block → 0.0 without a run; pass-count parsing for both runners; infra error
  raises. One Docker integration test per language behind the env flag.

### Task B: Rubric LLM judge

**Files:** Create `gatoway/judge.py`, `tests/test_judge.py`.

- [x] `judge(prompt, response, rubric: list[str], answer_model: str) -> float`.
  Each rubric item is a yes/no criterion; the judge returns JSON
  `{"criteria": [true, false, ...]}`; score = fraction true. Per-criterion
  booleans are more stable than a 1–10 scale and make disagreements readable.
- [x] **Judge model:** `openai/kimi`, temperature 0 — except when the answer
  came from `openai/kimi`, then `openai/glm-5`, so no model grades itself.
  Choose by `ProviderResponse.model_id` (the model that actually answered),
  **not** the rung: a `kimi`-rung answer may have come from its `glm-5`
  fallback via the circuit breaker. Call the judge with `call_provider`
  directly (concrete model string, no fallback); if the judge is down, raise
  — never substitute another judge.
  `ponytail:` a judge from the same ladder still shares biases; an
  off-ladder judge is the upgrade once a second provider key exists.
- [x] Malformed judge output → one retry, then raise (infra failure, not a
  0.0 score).
- [x] Calibration test (live, opt-in `GATOWAY_LIVE_TESTS=1`), run against
  **both** judge models since `kimi`'s answers get a different judge: each
  design task's reference answer scores ≥ 0.8; a one-line non-answer ≤ 0.2.
  Unit tests use a fake judge call.
- [x] Replace `score_llm_judge_stub` for **all** `llm_judge` tasks (the two
  existing eval tasks and the four existing train prompts get rubrics), so the
  eval has one judging standard. Keep the stub only for `--dry-run`.

### Task C: The problems

**Files:** `benchmarks/coding/{eval,train}/…`, extend `tests/test_bank_corpus.py`.

Each eval problem gets **two** train neighbors (same pattern, different
problem) so `MIN_OBSERVATIONS = 2` is reachable in its neighborhood.

| Neighborhood | Eval (held out) | Train neighbors |
|---|---|---|
| hash map (Py) | two-sum indices | first non-repeating char; group anagrams |
| intervals (Py) | merge intervals | insert interval; meeting rooms (min rooms) |
| graph BFS (Py) | shortest path in 0/1 grid | number of islands; rotting oranges |
| sliding window (TS) | longest substring w/o repeats | max sum subarray of size k; min window length ≥ target |
| stack (TS) | valid parentheses | daily temperatures; evaluate RPN |
| data structure (TS) | LRU cache class | min stack; time-based key-value store |
| system design | URL shortener | pastebin; distributed rate limiter |
| architecture | split a monolith's auth into a service | event-driven order pipeline; multi-tenant data isolation |

8 eval + 16 train. The eval problems are among the most memorized LeetCode
problems, so give at least two a non-standard twist (e.g. two-sum returning all
index pairs; LRU with per-key TTL) so scores spread across rungs instead of
every rung passing and measured difficulty collapsing to ~0. Train corpus grows 20 → 36 prompts (288 bootstrap calls,
plus ~96 judge calls).

- [x] Every reference passes its own hidden tests (local subprocess).
- [x] Cross-leak check: run each eval reference against every same-language
  train task's hidden tests **with the reference's function rebound to the
  train entrypoint name**, and vice versa; each must fail. Without the rebind
  the check passes trivially on an import error and proves nothing.
- [x] Every prompt passes the character-overlap guard.
- [x] Design rubrics: 4–6 concrete criteria each (e.g. "names a collision
  strategy for short codes"), not keywords.

### Task D: Eval harness — coding suite

**Files:** Modify `gatoway/eval.py`, its tests, `docs/eval_report.md` (regenerated).

- [x] New `scoring_method`s: `code_tests` and the real `llm_judge`.
- [x] **Run coding as a second simulated session**, not appended to the
  current one. The existing 8 tasks already form one deliberately overlong
  session with threshold shifting from turn 4; a 16-turn session would push
  the coding tasks to extreme thresholds and confound the result. The report
  shows per-suite and overall numbers.
- [x] Stability gate: `code_tests` tasks count as checkable **on pass/fail**
  (all hidden tests pass), not the fraction — 20–50-line answers at
  temperature 0 on hosted models are not run-to-run reproducible, and 7/10 vs
  8/10 would fail the gate for reasons unrelated to routing. The bank still
  stores the fraction. Judge-scored tasks stay excluded, as today.
- [x] `--dry-run` needs canned responses for the new tasks: use each task's
  reference as the high band and a truncated/incorrect variant as the low band.

---

## Follow-on edits

- DESIGN.md: new phase entry; flip the "Real LLM judge" deferred row; note the
  gate baseline break.
- Densification plan Task 3: bootstrap consumes `bank_corpus.score`, which now
  dispatches to `code_grader` and `judge`; Docker must be running.
- README: document the Docker + node image prerequisites.

## Open questions

- **Judge cost.** 64 judge calls per bootstrap plus 3 runs × 4 judged eval
  tasks × 2 sides per gate, before retries. Acceptable on NRP; revisit if rate-limited.
- **Partial-credit scores vs. the 0.7 effectiveness bar.** A rung passing 7/10
  hidden tests clears the bar. Probably right for routing, but watch it.

## Implementation status — 2026-09-30

Tasks A–D are implemented and validated. After user authorization, the live
calibration passed all 24 task/judge combinations in 514.37 seconds. Both
openai/kimi and openai/glm-5 scored each of the 12 reference answers at least
0.8 and its non-answer at most 0.2. See docs/judge_calibration.md.

Validation:
- Baseline before this expansion: 182 tests passed.
- Final ordinary suite: 323 passed, 27 opt-in tests skipped, with the same two
  dependency deprecation warnings. Skips comprise 24 judge calibrations and
  three Docker integration tests.
- Live rubric calibration: 24 passed, 12 non-calibration tests deselected.
- Docker grader suite: 20 passed, including Python and TypeScript reference
  execution, wrong-answer rejection, and legacy loop execution.
- Node 22's actual container passed the enum transformation probe, so no
  Node 24 fallback was needed.
- All 18 coding references pass locally; all 72 opposite-split same-language
  reference checks fail after entrypoint rebinding. All 36 train prompts and
  both seed sources pass the expanded eval overlap guard.
- Regenerated the three-run dry report. Preserved the preceding live report
  as docs/eval_report_pre_coding.md. These dry results are a harness smoke
  check and cannot establish live routing quality.

Implementation details:
- Live Python loop grading also uses Docker; only trusted canned/reference
  code is exercised on the host in offline checks.
- Dry runs use scripted coding scores and the heuristic judge, requiring
  neither Docker nor network.
- Shared async bank_corpus.score dispatches live code to Docker and all
  open-ended answers to the rubric judge. Infrastructure errors propagate.
- Coding generation has a 2048-token allowance; original tasks retain 512.
- Judge inference cost is explicitly excluded from answer cost comparisons.
- The measured bootstrap is complete: 288 rows in an isolated database;
  all 16 eval tasks have evidence on all eight rungs. The live gate is running.
- Following bootstrap fixes, the ordinary suite passed 340 tests with 28
  opt-in tests skipped and two existing dependency deprecation warnings.
  Regression checks cover Unicode minus, TypeScript signed zero, cached
  generation reuse after judge failures, and truncated-judge retry budgets.
