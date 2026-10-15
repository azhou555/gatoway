# Bank Densification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-labeled 24-row seed bank with a bank of *measured*
per-model outcomes that is dense within each semantic neighborhood, and close
the eval-prompt leakage that the current seed set contains — so the wide-ladder
gate measures routing rather than seeding.

**Architecture:** Follow-on to `docs/specs/2026-09-04-wide-ladder-design.md`
§8.1. That section diagnosed the failed ladder gate as insufficient evidence per
task cluster. The fix is a bootstrap harness that runs a **train-split** prompt
corpus across every rung, scores each response with the existing execution
scorers, and writes one `decision_history` row per (prompt, rung) pair. Each
prompt therefore contributes 8 rows at one point in embedding space, which is
exactly what `MIN_OBSERVATIONS = 2` needs and what the current bank lacks.

**Tech Stack:** Python 3.13, pytest (`asyncio_mode = "auto"`), litellm against
NRP's OpenAI-compatible endpoint, asyncpg + pgvector.

**Spec:** `docs/specs/2026-09-04-wide-ladder-design.md` §5.3, §8.1

---

## Why this over the alternatives

| Approach | Verdict |
|---|---|
| Cross-product of a train corpus over all rungs, auto-scored | **Chosen.** Observed outcomes, locally dense, no new scorers needed. |
| Cross-product over the **eval** tasks | Rejected — that is leakage by construction. |
| Manual difficulty labeling (`label_seed.py`) | Rejected — writes a guessed difficulty and a fixed 0.9 effectiveness. Not evidence. |
| Wait for real traffic via the batch job | Correct long term, useless now: there is no traffic. |

---

## Global Constraints

- The virtualenv is at `.venv/`. Run everything as `.venv/bin/python` and
  `.venv/bin/pytest` — a bare `python`/`pytest` will not have the project
  installed.
- `NRP_API_KEY` must be set in `.env`. `gatoway/providers.py` calls
  `load_dotenv()` at import.
- The full suite must stay green. Record the pre-plan count with
  `.venv/bin/pytest -q` before Task 1 and compare at the end.
- Deliberate simplifications get a `ponytail:` comment naming the ceiling and
  the upgrade path, matching `gatoway/providers.py` and `schema.sql`.
- **Do not add an ANN index to `decision_history`.** `schema.sql` documents why
  it was removed.
- **`decision_history` stores no prompt text**, only embeddings. Leakage checks
  therefore run against the *source prompt lists* in Python, not against the DB.
  This is the cheaper and more deterministic place to check anyway.
- Bootstrap runs write rows with real model outcomes. Run them against the
  isolated eval database, never against a bank holding unrelated local data.

---

### Task 1: Close the existing eval-prompt leakage

**Problem:** `gatoway/seed.py` contains prompts that are verbatim or
near-verbatim copies of `gatoway/eval.py:BENCHMARK_TASKS` prompts. Measured with
`difflib.SequenceMatcher`:

| Eval task | Seed prompt | Ratio |
|---|---|---|
| `capital_france` | identical | 1.00 |
| `sql_query` | identical | 1.00 |
| `hard_math_proof` | identical | 1.00 |
| `code_fix` | differs by one word | 0.98 |
| `multistep_planning` | reworded opening clause | ~0.9 |

The router matches on `input_embedding`, so a verbatim seed row returns
similarity ≈ 1.0 and the routing decision for that task is driven by a
hand-assigned rung rather than by learned evidence. Spec §7/§8 forbid exactly
this; the existing `is_train_split` gate never catches it because the leak is
introduced at seed time, not at write-back time.

**Files:**
- Test: `tests/test_bank_leakage.py` (create)
- Modify: `gatoway/seed.py` (rewrite the five colliding prompts)

**Interfaces:**
- Produces: `gatoway.bank_corpus.assert_no_eval_overlap(prompts)`, reused by
  Task 2's corpus test and Task 3's bootstrap entry point.

- [x] **Step 1: Write the failing test.** `tests/test_bank_leakage.py` collects
  every prompt in `seed.CHEAP_EXAMPLES + MEDIUM_EXAMPLES + FRONTIER_EXAMPLES`
  and every prompt in `label_seed.CANDIDATE_PROMPTS`, and asserts that none
  exceeds a similarity threshold against any `BENCHMARK_TASKS` prompt. Use two
  checks: exact-match (case- and whitespace-normalized) must be empty, and
  `difflib.SequenceMatcher` ratio must stay under `0.85`. The failure message
  must name the colliding pair and its ratio, or a future regression is
  unreadable. Expect 5 failures on first run.
- [x] **Step 2: Verify the test fails for the right reason** — five named
  collisions, not an import error.
- [x] **Step 3: Rewrite the five seed prompts** so they stay in the same
  semantic neighborhood without restating the eval task. Same topic, different
  instance:
  - `What is the capital of France?` → `What is the capital of Portugal?`
  - `Write a SQL query to find the second-highest salary from an employees
    table.` → `Write a SQL query to find the third-highest order total from an
    orders table.`
  - `Prove that the square root of 2 is irrational.` → `Prove that there are
    infinitely many prime numbers.`
  - `Fix the off-by-one bug: for i in range(1, n): print(arr[i])` → `Fix the
    off-by-one bug: for i in range(0, n+1): print(arr[i])`
  - `Plan a 3-step migration strategy from a monolith to microservices…` →
    `Plan a 3-step strategy for splitting a shared database between two teams,
    considering write contention.`
  Update each row's canned response text to match its new prompt.
- [x] **Step 4: Run the test — green.** Then `.venv/bin/pytest -q` for the full
  suite.
- [x] **Step 5: Record the finding** in `docs/specs/2026-09-04-wide-ladder-design.md`
  §8.1 as a correction: the first wide-ladder gate ran against a bank that
  leaked 5 of 8 eval prompts, so its effectiveness delta is not a clean
  measurement of routing. State it plainly — it is evidence about the gate, not
  a reason to hide the gate.

---

**Completed 2026-09-30.** Baseline: 100 tests passed. The normalized
0.85 guard found six seed collisions rather than the expected five: the Japan
capital question also matched at 0.881. All six prompts were rewritten, with
matching canned answers; the Portugal and loop examples needed more rewording
than the suggested substitutions to clear the threshold. All interactive
label candidates passed. The reusable guard lives in `gatoway/bank_corpus.py`
and accepts strings or records exposing `prompt`. Regression coverage: 47
tests; full suite: 147 passed (the same two dependency deprecation warnings).
Existing database rows are unchanged; Task 4 rebuilds the isolated bank.

### Task 2: Build the train-split prompt corpus

**Files:**
- Create: `gatoway/bank_corpus.py`
- Test: `tests/test_bank_corpus.py` (create)

**Interfaces:**
- Consumes: `gatoway.eval.BENCHMARK_TASKS` (for the overlap guard only),
  `gatoway.bank_corpus.score`-compatible scoring methods.
- Produces: `TRAIN_PROMPTS: list[TrainPrompt]` with fields `prompt_id`,
  `prompt`, `scoring_method`, `expected`, `neighborhood`. Consumed by Task 3.

**Design:** Two to three prompts per eval-task neighborhood, each with a
checkable answer, none overlapping an eval prompt. Neighborhoods mirror the
eval suite so the density lands where the gate measures:

| Neighborhood | Count | Scoring |
|---|---|---|
| factual recall | 3 | `exact_match` |
| arithmetic | 3 | `exact_match` |
| unit conversion | 2 | `exact_match` |
| algebra | 2 | `exact_match` |
| loop/off-by-one fixes | 3 | `python_execution` |
| SQL aggregate queries | 3 | `sql_execution` |
| systems planning | 2 | `llm_judge` |
| proofs | 2 | `llm_judge` |

20 prompts × 8 rungs = 160 rows, 160 model calls per bootstrap run.

- [x] **Step 1: Write the failing test.** Assert: every `prompt_id` is unique;
  every `scoring_method` is one `score_task` handles; every neighborhood has at
  least 2 prompts (so `MIN_OBSERVATIONS = 2` is satisfiable within it); and
  `assert_no_eval_overlap(TRAIN_PROMPTS)` passes.
- [x] **Step 2: Verify it fails** (the guard module exists after Task 1, but
  importing `TRAIN_PROMPTS` fails until the corpus is implemented).
- [x] **Step 3: Write `gatoway/bank_corpus.py`.** The `python_execution` and
  `sql_execution` prompts must be answerable within the scorers' constrained
  languages — a single `for` loop over `arr`/`n` for Python, a read-only
  `SELECT` for SQL. Reuse the existing scorers; do not write new ones. Add
  fixtures for any new SQL/Python shape, or reword the prompt to fit the
  existing fixtures — prefer rewording.
- [x] **Step 4: Green, then full suite.**

---

**Completed 2026-09-30.** Added 20 train prompts across all eight
neighborhoods, with reference answers and an explicit train split. The six
execution tasks use different outputs from the eval tasks; trusted fixtures
extend the existing constrained scorers without changing their default eval
fixtures. Tests reject eval answers on train fixtures and train references on
eval fixtures in both directions. All prompts pass the overlap guard.
Validation: 182 tests passed, up from 147, with the same two dependency
deprecation warnings. No provider calls or database writes were made.

**Coding expansion completed:** Tasks A–D in
`docs/plans/2026-09-24-coding-tasks.md`, then bootstrap Task 3 below.
All open-ended train tasks now use the calibrated rubric judge for live scoring.

### Task 3: Bootstrap harness

**Updated after coding expansion:** consume the 36-record corpus and await
bank_corpus.score(task, response.content, response.model_id). Docker must
be running with the Python and Node images available. Preserve fractional
code scores and propagate judge/container infrastructure errors; they must
never produce zero-score bank rows. Use the actual response model for judging.
For dry runs pass dry_run=True and write no bank rows.


**Files:**
- Create: `gatoway/bootstrap_bank.py`
- Test: `tests/test_bootstrap_bank.py` (create)

**Interfaces:**
- Consumes: `bank_corpus.TRAIN_PROMPTS`, `providers.MODEL_LADDER`,
  `providers.call_provider`, `bank_corpus.score`, `embeddings.embed`,
  `db.get_pool`.
- Produces: `decision_history` rows with `model_id` = the rung's primary,
  `calculated_effectiveness` = the measured score, `calculated_difficulty` =
  `1 − mean(score across rungs)` for that prompt, `confidence = 1.0` (an
  observed outcome, not a similarity match — matching `batch_job.py`'s
  convention), `session_id = NULL`.

- [x] **Step 1: Write the failing test** against a fake pool and a fake
  provider. Cover: every (prompt, rung) pair produces exactly one row; a scored
  0.0 response is still written (**failures are evidence** — this is the row
  that lets the bar reject a rung); a provider exception skips that pair without
  aborting the run; `--dry-run` writes nothing and makes no provider call.
- [x] **Step 2: Verify it fails.**
- [x] **Step 3: Implement.** Structure mirrors `eval.py`'s provider path:
  temperature 0, 512 tokens for original tasks / 2048 for coding, 120s timeout, one retry. Print progress per
  prompt. Two flags: `--dry-run` (canned responses, no DB) and `--rung NAME`
  (single rung, for iterating on the harness).
- [x] **Step 4: Compute difficulty from the cross-product, not by hand.** Once
  all 8 rungs have answered a prompt, `difficulty = 1 − mean(scores)` — a prompt
  every rung solves is easy, one only `kimi` solves is hard. This is the first
  difficulty figure in the project that is measured rather than guessed. Note
  it in the module docstring.
- [x] **Step 5: Green, then full suite.**

---

**Implemented and validated.** Baseline was 323 tests. The full suite
passed 336 tests after implementation; an additional opt-in local Postgres
integration test passed with fake providers. A complete dry run scored 288
pairs with no provider calls, embeddings, or writes.

The CLI requires a separately named, ownership-marked evaluation database.
Checkpointed outcomes are tied to task/scorer fingerprints; stable row IDs
make resuming idempotent. Each prompt commits atomically. Zero-score answers
are stored; failed provider pairs are omitted. Difficulty remains NULL for
incomplete or single-rung measurements, then updates once all eight models
are observed. Scorer infrastructure failures propagate.

### Task 4: Run it and re-gate

**Files:**
- Modify: `docs/specs/2026-09-04-wide-ladder-design.md` (§8.1 result)
- Regenerated: `docs/eval_report.md`
- Modify: `README.md` (headline numbers, currently stale from the pre-fix gate)

- [x] **Step 1: Rebuild the bank from scratch** in the isolated eval database:
  `db migrate`, then `bootstrap_bank`. Decide and record whether the 24
  hand-labeled seed rows are kept. **Recommendation: drop them.** Their
  effectiveness values are assumptions in the 0.85–0.98 band, so every one
  clears the 0.7 bar by construction and they dilute measured evidence with
  guesses. A measured-only bank is also a much stronger claim.
- [x] **Step 2: Sanity-check density before spending a gate run.** For each eval
  task prompt, query the bank the way `classify()` does and record how many
  rungs clear `CONFIDENCE_FLOOR` with ≥ `MIN_OBSERVATIONS` rows. If most tasks
  still see fewer than 2 rungs with evidence, the corpus needs more prompts per
  neighborhood — fix that before running the gate, not after.
- [x] **Step 3: Run the 3-run eval gate**, live, DB-backed. Completed October 4
  with the expanded 32-task suite and rubric-json-v2 against the frozen bank.
- [x] **Step 4: Record the result honestly**, pass or fail, in design §8.1. If
  the ladder still cannot beat the three-tier result, that is a finding about
  the ladder, not a reason to keep tuning the bank.
- [x] **Step 5: Update `README.md`** to match the completed expanded report.
- [ ] **Step 6: Consider pruning dead rungs.** §3.3 of the design promised rungs
  would be removed on evidence. With a dense measured bank, a rung the router
  never selects is finally meaningful evidence rather than an artifact of
  sparsity.

---

## Open questions

- **Does a measured bank make `EFFECTIVENESS_BAR = 0.7` tunable?** It should —
  real scores will span 0.0 to 1.0 instead of clustering at 0.85–0.98. Tuning
  is still gated on the judge-scored tasks, which remain noisy. Sweep only the
  6 checkable tasks if you sweep at all.
- **Should the corpus grow by paraphrase augmentation?** 3 rewordings per prompt
  would take the bank from 160 to ~480 rows with no new scorers. Cheap, and the
  obvious next lever if Task 4 Step 2 shows thin neighborhoods. Deferred until
  measured density says it is needed.
- **Should `bootstrap_bank` replace `seed.py` entirely?** Probably, once it
  works. `label_seed.py` keeps its value for growing coverage into
  neighborhoods with no automated scorer.

## Live execution — 2026-09-30

Explicit user authorization covered train/eval prompts, generated answers and
rubrics sent to NRP. The measured-only database
`gatoway_eval_measured_20260930` contains **288 observations**: 36 prompts ×
eight primary models. No historical seed rows were copied. The original
`gatoway` database retains its 106 rows unchanged.

All saved outcomes, row IDs, difficulties, confidence values and fingerprints
passed integrity checks. Every eval task has at least two qualifying neighbors
on all eight rungs under the production query. See
[bank density](../bank_density.md) and [bootstrap report](../bootstrap_report.md).

**Historical partial attempt:** the live gate was resumed sequentially on 2026-10-03 against this
frozen bank. One repetition completed; repetition two is blocked on GLM-5
returning truncated, invalid rubric JSON for the saved baseline
authentication-design answer, including after a separate resume attempt.
The sequential attempt has not reached repetition three. The first repetition
shows 93.7% lower cost proxy and a 0.47-point quality decrease; it does not
establish accuracy preservation or stability. See [the partial live report](../eval_report.md).
Reliable structured rubric output is now the immediate prerequisite; any
scorer change needs validation and checkpoint/bank compatibility review.
Each repetition has independent sessions. Completed runs
are checkpointed in artifacts/gatoway_eval_measured_20260930/eval_runs.json.
The runner is saved beside that checkpoint. Standard sequential reproduction:

~~~bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m gatoway.bootstrap_bank \
  --database gatoway_eval_measured_20260930 --concurrency 4
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m gatoway.bank_density \
  --database gatoway_eval_measured_20260930
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m gatoway.eval \
  --database gatoway_eval_measured_20260930 --require-db --runs 3 \
  --checkpoint artifacts/measured_eval_sequential.json
~~~

**Completed follow-up, 2026-10-04:** all three repetitions of the 32-task
expanded suite completed with rubric-json-v2 and fresh responses, retaining
the frozen bank's historical training scores. The result is 92.2% lower cost
proxy but a 3.33-point quality loss (89.32% versus 92.66%) and failed stability.
See [the completed live report](../eval_report_expanded.md). All bank row values
were unchanged. Checkpoints are under `artifacts/expanded_eval_v2_20261003/`.
The scorer/task changes mean the historical checkpoints above must not be
resumed as current scores; this was a separately versioned evaluation.

The sequential CLI uses a separate checkpoint format/path. For the historical
16-task suite, expected calls before retries were 288 train generations +
64 train rubric judgments, then 96 eval generations + 24 eval rubric judgments.
The completed 32-task suite used 192 answer responses and 24 rubric judgments,
plus retries; it did not regenerate or regrade the training bank.
