# Eval Report: Router vs Always-Highest-Rung Baseline

**Monetary comparison:** see [OpenRouter pricing](openrouter_cost_comparison.md):
25.5% estimated savings on 54/96 matched pairs; full-suite savings unavailable.
The proxy tables below are preserved historical diagnostics.

_Real calls against NRP-hosted models._ _Cost is a parameter-count proxy, not real spend: NRP has no per-token billing, so each model is priced at its published parameter count in billions per 1M tokens. Its ordering does not reflect published token prices._

_Scoring: exact match for factual tasks; constrained Python/SQLite fixtures for legacy tasks; Docker execution for all Python/TypeScript answers; rubric LLM judging for all open-ended tasks (judge overhead excluded from answer cost)._

_Session evaluation: four independent eight-turn sessions per run; expected turn count 3; thresholds therefore rise on later turns._

_Judge version: rubric-json-v2. Strict whole-response JSON equality grades the breadth tasks._

Breadth tasks are held-out generalization challenges; the historical training bank has not been expanded to cover them. Report their quality separately from the original suites.

_Routing: DB-backed pgvector `decision_history` lookup (288 rows)._

_Generation controls: temperature 0, maximum 512 tokens for original and breadth tasks / 2048 for coding, 120s timeout, 1 timeout retry._

**Headline across 3 runs: 92.2% (91.4%–92.7%) cost-proxy reduction, -3.3 pt (-7.0 pt to +0.0 pt) effectiveness delta vs always-highest-rung.**

Expanded suite: a new baseline; not comparable to historical eight-task gates.

**Stability gate: FAIL** — unstable scores: router/code_fix, router/injected_document, router/two_sum_pairs.

| Suite/Turn | Task | Threshold | Router Tier(s) | Router Cost Proxy (arbitrary units) mean (range) | Router Score mean (range) | Baseline Cost Proxy (arbitrary units) mean (range) | Baseline Score mean (range) |
|---:|---|---:|---|---:|---:|---:|---:|
| original/1 | capital_france | 0.50 | gemma-small | 0.000 | 1.00 | 0.051 (0.042–0.069) | 1.00 |
| original/2 | arithmetic | 0.50 | gemma-small | 0.000 | 1.00 | 0.068 (0.059–0.074) | 1.00 |
| original/3 | unit_conversion | 0.50 | gemma-small | 0.002 | 1.00 | 0.098 (0.072–0.148) | 1.00 |
| original/4 | quadratic_roots | 0.63 | gemma-small | 0.006 (0.006–0.007) | 1.00 | 0.160 (0.157–0.164) | 1.00 |
| original/5 | code_fix | 0.77 | glm-5 | 0.410 | 0.67 (0.00–1.00) | 0.238 (0.224–0.253) | 1.00 |
| original/6 | sql_query | 0.90 | gemma-small | 0.006 | 1.00 | 0.420 (0.375–0.477) | 1.00 |
| original/7 | multistep_planning | 0.90 | qwen3-small | 0.016 | 0.50 (0.25–0.75) | 0.542 | 0.25 (0.25–0.25) |
| original/8 | hard_math_proof | 0.90 | gemma-small | 0.006 | 0.75 (0.75–0.75) | 0.499 (0.490–0.510) | 1.00 (1.00–1.00) |
| coding/1 | auth_extraction | 0.50 | gemma-small | 0.013 | 0.80 (0.80–0.80) | 2.091 | 0.40 (0.00–0.80) |
| coding/2 | grid_shortest_path | 0.50 | gemma-small | 0.006 | 1.00 | 1.043 (0.742–1.405) | 1.00 |
| coding/3 | longest_unique | 0.50 | gpt-oss | 0.107 (0.084–0.140) | 1.00 | 0.522 (0.468–0.623) | 1.00 |
| coding/4 | lru_ttl | 0.63 | gemma-small | 0.008 | 1.00 | 2.182 | 0.00 |
| coding/5 | merge_intervals | 0.77 | qwen3-small | 0.017 (0.015–0.019) | 1.00 | 0.597 (0.490–0.747) | 1.00 |
| coding/6 | two_sum_pairs | 0.90 | qwen3-small | 0.052 (0.046–0.059) | 0.67 (0.00–1.00) | 1.207 (0.519–1.851) | 1.00 |
| coding/7 | url_shortener | 0.90 | qwen3-small | 0.058 | 0.87 (0.60–1.00) | 2.087 | 1.00 (1.00–1.00) |
| coding/8 | valid_parentheses | 0.90 | gpt-oss | 0.055 (0.053–0.055) | 1.00 | 0.508 (0.494–0.526) | 1.00 |
| structured/1 | invoice_extraction | 0.50 | gpt-oss | 0.034 | 1.00 | 0.186 (0.182–0.192) | 1.00 |
| structured/2 | missing_fields | 0.50 | gpt-oss | 0.038 (0.037–0.038) | 1.00 | 0.181 (0.176–0.186) | 1.00 |
| structured/3 | injected_document | 0.50 | gpt-oss | 0.063 (0.058–0.066) | 0.33 (0.00–1.00) | 0.227 (0.207–0.246) | 1.00 |
| structured/4 | latest_status | 0.63 | gemma-small | 0.002 | 1.00 | 0.235 (0.204–0.298) | 1.00 |
| structured/5 | stable_dedup | 0.77 | gemma-small | 0.001 | 1.00 | 0.243 (0.230–0.262) | 1.00 |
| structured/6 | aggregate_events | 0.90 | gpt-oss | 0.032 (0.031–0.034) | 1.00 | 0.202 (0.201–0.202) | 1.00 |
| structured/7 | priority_classification | 0.90 | gpt-oss | 0.047 (0.047–0.048) | 1.00 | 0.261 (0.261–0.262) | 1.00 |
| structured/8 | exact_output_contract | 0.90 | gpt-oss | 0.031 (0.031–0.032) | 1.00 | 0.195 (0.191–0.198) | 1.00 |
| reasoning/1 | discount_tax | 0.50 | gpt-oss | 0.035 | 1.00 | 0.176 | 1.00 |
| reasoning/2 | weighted_average | 0.50 | gpt-oss | 0.027 | 1.00 | 0.137 (0.137–0.138) | 1.00 |
| reasoning/3 | schedule_constraints | 0.50 | gemma-small | 0.001 | 1.00 | 0.301 (0.230–0.343) | 1.00 |
| reasoning/4 | capacity_planning | 0.63 | gemma-small | 0.001 | 0.00 | 0.315 (0.308–0.323) | 1.00 |
| reasoning/5 | interval_boundaries | 0.77 | gemma-small | 0.001 | 1.00 | 0.357 (0.330–0.395) | 1.00 |
| reasoning/6 | logic_entailment | 0.90 | gpt-oss | 0.058 (0.056–0.061) | 1.00 | 0.282 (0.278–0.290) | 1.00 |
| reasoning/7 | answerability | 0.90 | gpt-oss | 0.029 | 1.00 | 0.189 (0.185–0.195) | 1.00 |
| reasoning/8 | long_context_override | 0.90 | gpt-oss | 0.177 | 1.00 | 1.387 (1.386–1.389) | 1.00 |

**Session totals (mean and range)** — Router: 1.339 (1.315–1.370), 89.3% (86.9%–92.7%) effective. Highest-rung baseline: 17.185 (15.898–18.049), 92.7% (91.4%–93.9%) effective.

## Per-suite results

| Suite | Router effectiveness | Baseline effectiveness | Cost reduction |
|---|---:|---:|---:|
| original | 86.5% (81.2%–90.6%) | 90.6% | 78.4% (77.7%–78.9%) |
| coding | 91.7% (85.0%–97.5%) | 80.0% (75.0%–85.0%) | 96.9% (96.2%–97.3%) |
| structured | 91.7% (87.5%–100.0%) | 100.0% | 85.7% (85.1%–86.1%) |
| reasoning | 87.5% | 100.0% | 89.6% (89.2%–89.8%) |

## Execution provenance

Isolated database: gatoway_eval_measured_20260930. Three independent repetitions ran sequentially with fresh answer generations; each retained its own four eight-turn sessions. The bank retained its historical training scores and was read-only throughout. Evaluation uses rubric-json-v2; this is a frozen-policy generalization test, not a regraded or expanded training bank. Generation and judge calls used the configured NRP endpoint. Judge calls begin with 1024 tokens and a 120-second timeout; an infrastructure/format failure permits one 4096-token/240-second retry. Judge overhead is excluded from answer cost.

Router selection counts across 96 task-runs: gemma-small=42, glm-5=3, qwen3-small=12, gpt-oss=39.

## Completed-run audit — 2026-10-04

All **96 task comparisons / 192 answer responses** are present and scored.
The collector checked all database row values before and after the run;
the 288-row bank was unchanged. Checkpoint results agree with saved answer
costs and scores, and all 96 breadth-answer JSON scores were independently
recomputed locally. Artifacts are in `artifacts/expanded_eval_v2_20261003/`:
`live_gate.py`, `eval_runs.json`, `eval_partial_1.json` through
`eval_partial_3.json`, and `analysis.json`. The artifact directory retains the
run's original date; collection completed October 4.

### Measured outcomes and limits

| Metric | Router | Always-highest-rung baseline |
|---|---:|---:|
| Mean task quality | 89.32% | 92.66% |
| Fully passing objective task-runs | 77/84 (91.7%) | 81/84 (96.4%) |
| Reported answer tokens | 49,535 | 51,555 |
| Summed provider-call time | 857.9s | 2,336.9s |
| Answers ending at token limit | 15/96 | 12/96 |

The provider-call time reduction is **63.3%**, excluding judging, grading,
embedding, and database overhead. Reported answer tokens fell **3.9%**.
The much larger **92.2% mean cost-proxy reduction** therefore mainly reflects
parameter-count weighting, not token savings. It is not billed savings or
measured GPU compute. Calls that time out without usage metadata cannot
contribute tokens to these totals; the successful provider wrapper's timing
includes its internal retry. One URL-shortener generation timed out and
recovered on its configured retry.

Objective tasks are 28 distinct tasks repeated three times, not 84 independent
problem types. Quality averages also include fractional rubric scores. Ranges
across three runs are not confidence intervals or a noninferiority test.
The 32-task mix, changed judge, and frozen historical training scores prevent
a direct comparison with historical 8- or 16-task headline numbers.

### Concrete regressions

- **Capacity planning:** router 0/3 versus baseline 3/3. The routed Gemma answer
  consistently chose B+C (value 11); C+D fits the capacity and yields value 14.
  This is a wrong answer, not a formatting or truncation failure.
- **Injected-document extraction:** router 1/3 versus baseline 3/3. GPT-OSS
  refused the extraction request in two runs instead of returning the requested
  JSON. These were refusals, not observed compliance with the injected payload.
- **Code fix and two-sum:** router 2/3 full passes on each versus baseline 3/3.
  Their changing pass/fail outcomes, together with injected_document, fail the
  stability gate. Stable failure on capacity planning is also a quality problem
  even though a repeatability-only gate does not flag it.
- **LRU expiry:** router 3/3 versus baseline 0/3. The baseline hit its answer
  token limit in all three runs. This contributes to the routed coding-suite
  advantage and reinforces the fixed-output-budget limitation.

### Judge reliability during the evaluation

All **24 required rubric judgments** eventually completed. **21/24** were
valid on the first attempt; 29 total attempts included **five truncated
responses**. All five occurred while Kimi graded routed multistep-planning
answers. Repetition two exhausted both configured attempts and stopped; a
checkpointed resume regraded the same saved answer, requiring two more
attempts. The other two repetitions recovered within their configured retry.
These attempts remain in `judge_attempts`; no failures became fabricated
zero scores and no successful answer was regenerated to improve its score.

Total judge-call time was **930.8s**, excluded from answer-latency and cost-proxy
comparisons. The earlier 54/54 first-attempt calibration result did not
establish the same reliability on generated answers. Further judge hardening
should include these saved failure cases and keep output reliability separate
from agreement on rubric quality.

### Conclusion and next experiments

This run measures substantial proxy savings with **a 3.33 percentage-point
mean quality loss and failed stability**, not accuracy-preserving savings.
The next experiments should separately address output-budget/truncation
behavior, routing on constraint-solving tasks, and unnecessary refusals on
untrusted-document extraction. Add distinct training examples for the new
categories and keep an untouched holdout for validation; do not seed with
these evaluation prompts or tune to a single failing example.
