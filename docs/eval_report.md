# Eval Report: Router vs Always-Highest-Rung Baseline

> Historical partial result. The completed 32-task, three-run evaluation is
> in [eval_report_expanded.md](eval_report_expanded.md). Its changed task mix
> and judge configuration establish a separate baseline.

> **Partial live result, recorded 2026-10-03: only 1 of 3 repetitions complete.**
> Repetition 2 stopped on the baseline authentication-design rubric judgment;
> a separate resume attempt failed on that same saved answer. Repetition 3
> has not run in this sequential attempt. This is not an accuracy-preservation
> or stability claim. Identical single-run ranges below do not measure uncertainty.

> This report preserves the original judge's results. The subsequent
> `rubric-json-v2` change and opt-in 32-task suite have not been measured here;
> see [judge reliability](judge_reliability.md) and [task breadth](evaluation_breadth.md).

_Real calls against NRP-hosted models._ _Cost is a parameter-count proxy, not real spend: NRP has no per-token billing, so each model is priced at its published parameter count in billions per 1M tokens. Only relative ordering is meaningful._

_Scoring: exact match for factual tasks; constrained Python/SQLite fixtures for legacy tasks; Docker execution for all Python/TypeScript answers; rubric LLM judging for all open-ended tasks (judge overhead excluded from answer cost)._

_Session evaluation: two independent eight-turn sessions per run; expected turn count 3; thresholds therefore rise on later turns._

_Routing: DB-backed pgvector `decision_history` lookup (288 rows)._

_Generation controls: temperature 0, maximum 512 tokens for original tasks / 2048 for coding, 120s timeout, 1 timeout retry._

**Headline across 1 runs: 93.7% (93.7%–93.7%) cost-proxy reduction, -0.5 pt (-0.5 pt to -0.5 pt) effectiveness delta vs always-highest-rung.**

Expanded suite: a new baseline; not comparable to historical eight-task gates.

**Stability gate: NOT EVALUATED** — 1/3 required runs complete.

| Suite/Turn | Task | Threshold | Router Tier(s) | Router Cost Proxy (arbitrary units) mean (range) | Router Score mean (range) | Baseline Cost Proxy (arbitrary units) mean (range) | Baseline Score mean (range) |
|---:|---|---:|---|---:|---:|---:|---:|
| original/1 | capital_france | 0.50 | gemma-small | 0.000 | 1.00 | 0.041 | 1.00 |
| original/2 | arithmetic | 0.50 | gemma-small | 0.000 | 1.00 | 0.074 | 1.00 |
| original/3 | unit_conversion | 0.50 | gemma-small | 0.002 | 1.00 | 0.148 | 1.00 |
| original/4 | quadratic_roots | 0.63 | gemma-small | 0.007 | 1.00 | 0.158 | 1.00 |
| original/5 | code_fix | 0.77 | glm-5 | 0.410 | 0.00 | 0.239 | 1.00 |
| original/6 | sql_query | 0.90 | gemma-small | 0.006 | 1.00 | 0.385 | 1.00 |
| original/7 | multistep_planning | 0.90 | qwen3-small | 0.016 | 0.50 (0.50–0.50) | 0.542 | 0.25 (0.25–0.25) |
| original/8 | hard_math_proof | 0.90 | gemma-small | 0.006 | 0.75 (0.75–0.75) | 0.531 | 1.00 (1.00–1.00) |
| coding/1 | auth_extraction | 0.50 | gemma-small | 0.014 | 0.80 (0.80–0.80) | 2.091 | 0.20 (0.20–0.20) |
| coding/2 | grid_shortest_path | 0.50 | gemma-small | 0.006 | 1.00 | 1.275 | 1.00 |
| coding/3 | longest_unique | 0.50 | gpt-oss | 0.098 | 1.00 | 0.625 | 1.00 |
| coding/4 | lru_ttl | 0.63 | gemma-small | 0.008 | 1.00 | 2.182 | 0.00 |
| coding/5 | merge_intervals | 0.77 | qwen3-small | 0.016 | 1.00 | 0.868 | 1.00 |
| coding/6 | two_sum_pairs | 0.90 | qwen3-small | 0.059 | 0.12 | 0.678 | 1.00 |
| coding/7 | url_shortener | 0.90 | qwen3-small | 0.058 | 1.00 (1.00–1.00) | 2.087 | 0.80 (0.80–0.80) |
| coding/8 | valid_parentheses | 0.90 | gpt-oss | 0.072 | 1.00 | 0.489 | 1.00 |

**Session totals (mean and range)** — Router: 0.778 (0.778–0.778), 82.3% (82.3%–82.3%) effective. Highest-rung baseline: 12.413 (12.413–12.413), 82.8% (82.8%–82.8%) effective.

## Per-suite results

| Suite | Router effectiveness | Baseline effectiveness | Cost reduction |
|---|---:|---:|---:|
| original | 78.1% | 90.6% | 78.9% |
| coding | 86.6% | 75.0% | 96.8% |
## Execution provenance and blocker

The runner verified the frozen bank/code/task signature before resuming.
Database: `gatoway_eval_measured_20260930`, with 288 measured training rows.
This run reused valid responses and scores saved during the previous attempt,
so it is not a set of entirely fresh October 3 generations. New calls went to
`https://ellm.nrp-nautilus.io/v1` with explicit user approval.

Repetition 2 has 18 saved answers and 17 saved scores. Its outstanding
`auth_extraction/baseline/kimi` judgment uses `openai/glm-5`. Both the initial
attempt and the resumed attempt exhausted the rubric judge's output allowance
without valid JSON (`finish_reason=length`), including its 4096-token retry.
The harness raised `JudgeInfrastructureError`; no fabricated score was stored.
Historical errors for repetition 3 in the checkpoint belong to the earlier
concurrent attempt, not a new third repetition.

Checkpoints and the resumable runner are in
`artifacts/gatoway_eval_measured_20260930/` (ignored by Git).
The first complete repetition is in `eval_runs.json`; individual answers and
scores are in `eval_partial_1.json` and `eval_partial_2.json`.

## Interpretation and next work

The first repetition scores 82.34375% routed versus 82.8125% baseline:
**93.7% lower cost proxy and a 0.47 percentage-point quality decrease**.
The aggregate masks task-level regressions: code_fix scores 0 versus 1,
and two_sum_pairs scores 0.125 versus 1. The routed path improves on other
tasks, including lru_ttl (1 versus 0).

The routed code_fix and two_sum_pairs failures and the baseline lru_ttl
failure all hit their answer token limits. These are results under the fixed
512/2048-token allowances, not unrestricted model capability rankings.
The proxy uses total parameters times tokens, not billed spend or measured
GPU compute; judge overhead is excluded.

The next prerequisite for a completed repeated measurement is reliable,
validated structured rubric output. Any scorer change must be versioned and
its effect on existing bank/checkpoint scores assessed before reuse. Keep
infrastructure failures distinct from answer failures. After completing the
three repetitions, assess both aggregate quality and per-task regressions;
the existing stability gate checks repeatability, not quality equivalence.

Local preflight on October 3: 340 ordinary tests passed (28 skipped),
20 Docker grader tests passed, and all 16 eval tasks had evidence on all
eight rungs. No additional routing feature or bank expansion was required.
