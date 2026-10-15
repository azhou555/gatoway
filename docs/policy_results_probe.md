# Policy screening results

**Status: 526/528 unique task/model/repetition outcomes scored.**

[Protocol and limitations](policy_comparison.md). Prices include the unverified Gemma rate assumption. All policies share the same generation controls and matched answers. No production policy was changed.

## All

| Policy | Scored pairs | Quality (raw) | Delta raw (pts) | Exploratory 95% interval | Quality (fence-norm) | Delta norm (pts) | Estimated USD | Savings | Length finishes |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| current | 232 (2 missing) | 70.32% | -28.81 | [-38.40, -19.27] | 93.60% | -5.97 | $0.215746 | 2.0% | 3 |
| frontier_fallback | 232 (2 missing) | 73.77% | -25.37 | [-34.83, -16.24] | 95.75% | -3.81 | $0.247422 | -12.4% | 3 |
| paired_quality | 232 (2 missing) | 79.63% | -19.50 | [-28.42, -10.58] | 99.46% | -0.11 | $0.255350 | -16.0% | 0 |
| price_order | 232 (2 missing) | 73.17% | -25.97 | [-35.68, -16.35] | 95.15% | -4.42 | $0.086354 | 60.8% | 0 |
| strict_evidence | 232 (2 missing) | 79.74% | -19.40 | [-28.21, -10.26] | 99.57% | +0.00 | $0.212217 | 3.6% | 0 |
| paired_price | 232 (2 missing) | 79.74% | -19.40 | [-28.21, -10.26] | 99.57% | +0.00 | $0.212217 | 3.6% | 0 |
| always_kimi | 232 (2 missing) | 99.14% | +0.00 | [+0.00, +0.00] | 99.57% | +0.00 | $0.220176 | 0.0% | 0 |

## Existing

| Policy | Scored pairs | Quality (raw) | Delta raw (pts) | Exploratory 95% interval | Quality (fence-norm) | Delta norm (pts) | Estimated USD | Savings | Length finishes |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| current | 94 (2 missing) | 89.52% | -10.48 | [-20.26, -1.04] | 89.52% | -10.48 | $0.173634 | -7.7% | 3 |
| frontier_fallback | 94 (2 missing) | 92.71% | -7.29 | [-16.25, -0.26] | 92.71% | -7.29 | $0.189509 | -17.6% | 3 |
| paired_quality | 94 (2 missing) | 99.73% | -0.27 | [-0.78, +0.00] | 99.73% | -0.27 | $0.192738 | -19.6% | 0 |
| price_order | 94 (2 missing) | 93.35% | -6.65 | [-15.89, +0.00] | 93.35% | -6.65 | $0.046196 | 71.3% | 0 |
| strict_evidence | 94 (2 missing) | 100.00% | +0.00 | [+0.00, +0.00] | 100.00% | +0.00 | $0.149678 | 7.1% | 0 |
| paired_price | 94 (2 missing) | 100.00% | +0.00 | [+0.00, +0.00] | 100.00% | +0.00 | $0.149678 | 7.1% | 0 |
| always_kimi | 94 (2 missing) | 100.00% | +0.00 | [+0.00, +0.00] | 100.00% | +0.00 | $0.161181 | 0.0% | 0 |

## Holdout

| Policy | Scored pairs | Quality (raw) | Delta raw (pts) | Exploratory 95% interval | Quality (fence-norm) | Delta norm (pts) | Estimated USD | Savings | Length finishes |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| current | 48 (0 missing) | 70.83% | -25.00 | [-43.75, -8.33] | 89.58% | -8.33 | $0.001661 | 92.1% | 0 |
| frontier_fallback | 48 (0 missing) | 81.25% | -14.58 | [-31.25, +0.00] | 93.75% | -4.17 | $0.017462 | 17.5% | 0 |
| paired_quality | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | 97.92% | +0.00 | $0.022162 | -4.7% | 0 |
| price_order | 48 (0 missing) | 77.08% | -18.75 | [-39.58, -2.08] | 89.58% | -8.33 | $0.001685 | 92.0% | 0 |
| strict_evidence | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | 97.92% | +0.00 | $0.021160 | 0.0% | 0 |
| paired_price | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | 97.92% | +0.00 | $0.021160 | 0.0% | 0 |
| always_kimi | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | 97.92% | +0.00 | $0.021160 | 0.0% | 0 |

## Probe

| Policy | Scored pairs | Quality (raw) | Delta raw (pts) | Exploratory 95% interval | Quality (fence-norm) | Delta norm (pts) | Estimated USD | Savings | Length finishes |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| current | 90 (0 missing) | 50.00% | -50.00 | [-66.67, -33.33] | 100.00% | +0.00 | $0.040451 | -6.9% | 0 |
| frontier_fallback | 90 (0 missing) | 50.00% | -50.00 | [-66.67, -33.33] | 100.00% | +0.00 | $0.040451 | -6.9% | 0 |
| paired_quality | 90 (0 missing) | 50.00% | -50.00 | [-66.67, -33.33] | 100.00% | +0.00 | $0.040451 | -6.9% | 0 |
| price_order | 90 (0 missing) | 50.00% | -50.00 | [-66.67, -33.33] | 100.00% | +0.00 | $0.038472 | -1.7% | 0 |
| strict_evidence | 90 (0 missing) | 50.00% | -50.00 | [-66.67, -33.33] | 100.00% | +0.00 | $0.041379 | -9.4% | 0 |
| paired_price | 90 (0 missing) | 50.00% | -50.00 | [-66.67, -33.33] | 100.00% | +0.00 | $0.041379 | -9.4% | 0 |
| always_kimi | 90 (0 missing) | 100.00% | +0.00 | [+0.00, +0.00] | 100.00% | +0.00 | $0.037835 | 0.0% | 0 |

Raw = strict whole-response JSON (counts a code fence as a miss, i.e. instruction-following). Fence-norm = same scoring after removing a single surrounding code fence (capability). They differ only on json_exact suites.

## Category quality deltas

Points relative to Kimi; negative means worse.

| Policy | coding | holdout_reasoning | holdout_structured | original | probe_gemma | probe_glm5 | reasoning | structured |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | -16.36 | -20.83 | -29.17 | -1.04 | -100.00 | +0.00 | -12.50 | -12.50 |
| frontier_fallback | -16.36 | -20.83 | -8.33 | -1.04 | -100.00 | +0.00 | -12.50 | +0.00 |
| paired_quality | +0.00 | +0.00 | +0.00 | -1.04 | -100.00 | +0.00 | +0.00 | +0.00 |
| price_order | +0.00 | -8.33 | -29.17 | -1.04 | -100.00 | +0.00 | -12.50 | -12.50 |
| strict_evidence | +0.00 | +0.00 | +0.00 | +0.00 | -100.00 | +0.00 | +0.00 | +0.00 |
| paired_price | +0.00 | +0.00 | +0.00 | +0.00 | -100.00 | +0.00 | +0.00 | +0.00 |
| always_kimi | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |

## Category quality deltas (fence-normalized)

Same as above after removing a single surrounding code fence; differs only on json_exact suites.

| Policy | coding | holdout_reasoning | holdout_structured | original | probe_gemma | probe_glm5 | reasoning | structured |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | -16.36 | -8.33 | -8.33 | -1.04 | +0.00 | +0.00 | -12.50 | -12.50 |
| frontier_fallback | -16.36 | -8.33 | +0.00 | -1.04 | +0.00 | +0.00 | -12.50 | +0.00 |
| paired_quality | +0.00 | +0.00 | +0.00 | -1.04 | +0.00 | +0.00 | +0.00 | +0.00 |
| price_order | +0.00 | -8.33 | -8.33 | -1.04 | +0.00 | +0.00 | -12.50 | -12.50 |
| strict_evidence | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |
| paired_price | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |
| always_kimi | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |

## Routing mix

| Policy | Model counts across task/repetitions |
|---|---|
| current | {'gemma-small': 94, 'glm-5': 45, 'qwen3-small': 15, 'gpt-oss': 78} |
| frontier_fallback | {'gemma-small': 94, 'glm-5': 45, 'qwen3-small': 15, 'gpt-oss': 6, 'kimi': 72} |
| paired_quality | {'kimi': 96, 'gemma-small': 63, 'glm-5': 51, 'qwen3-small': 15, 'gpt-oss': 7} |
| price_order | {'gpt-oss': 124, 'glm-5': 45, 'gemma-small': 60, 'qwen3-small': 3} |
| strict_evidence | {'kimi': 129, 'glm-5': 48, 'gemma-small': 48, 'gpt-oss': 7} |
| paired_price | {'kimi': 129, 'glm-5': 48, 'gemma-small': 48, 'gpt-oss': 7} |
| always_kimi | {'kimi': 232} |

## Objective full passes and repeatability

| Policy | Full passes | Scored objective answers | Unstable task IDs |
|---|---:|---:|---|
| current | 157 | 222 | holdout_untrusted |
| frontier_fallback | 165 | 222 | none |
| paired_quality | 175 | 222 | holdout_null, holdout_calendar |
| price_order | 160 | 222 | holdout_untrusted |
| strict_evidence | 175 | 222 | holdout_null, holdout_calendar |
| paired_price | 175 | 222 | holdout_null, holdout_calendar |
| always_kimi | 218 | 220 | holdout_null, holdout_calendar |

## Objective task failures and repeatability

Full pass means score 1.0. A stable failure is still a failure. Open-ended rubric tasks are excluded from this table.

| Policy | Task | Scores by repetition |
|---|---|---|
| current | injected_document | [0.0, 0.0, 0.0] |
| current | capacity_planning | [0.0, 0.0, 0.0] |
| current | holdout_null | [0.0, 0.0, 0.0] |
| current | holdout_untrusted | [0.0, 0.0, 1.0] |
| current | holdout_filter | [0.0, 0.0, 0.0] |
| current | holdout_selection | [0.0, 0.0, 0.0] |
| current | holdout_calendar | [0.0, 0.0, 0.0] |
| current | probe_sql_00 | [0.0, 0.0, 0.0] |
| current | probe_sql_01 | [0.0, 0.0, 0.0] |
| current | probe_sql_02 | [0.0, 0.0, 0.0] |
| current | probe_sql_03 | [0.0, 0.0, 0.0] |
| current | probe_sql_04 | [0.0, 0.0, 0.0] |
| current | probe_sql_05 | [0.0, 0.0, 0.0] |
| current | probe_sql_06 | [0.0, 0.0, 0.0] |
| current | probe_sql_07 | [0.0, 0.0, 0.0] |
| current | probe_sql_08 | [0.0, 0.0, 0.0] |
| current | probe_sql_09 | [0.0, 0.0, 0.0] |
| current | probe_sql_10 | [0.0, 0.0, 0.0] |
| current | probe_sql_11 | [0.0, 0.0, 0.0] |
| current | probe_sql_12 | [0.0, 0.0, 0.0] |
| current | probe_sql_13 | [0.0, 0.0, 0.0] |
| current | probe_sql_14 | [0.0, 0.0, 0.0] |
| frontier_fallback | capacity_planning | [0.0, 0.0, 0.0] |
| frontier_fallback | holdout_null | [0.0, 0.0, 0.0] |
| frontier_fallback | holdout_selection | [0.0, 0.0, 0.0] |
| frontier_fallback | holdout_calendar | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_00 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_01 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_02 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_03 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_04 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_05 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_06 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_07 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_08 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_09 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_10 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_11 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_12 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_13 | [0.0, 0.0, 0.0] |
| frontier_fallback | probe_sql_14 | [0.0, 0.0, 0.0] |
| paired_quality | holdout_null | [1.0, 1.0, 0.0] |
| paired_quality | holdout_calendar | [0.0, 1.0, 1.0] |
| paired_quality | probe_sql_00 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_01 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_02 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_03 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_04 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_05 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_06 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_07 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_08 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_09 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_10 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_11 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_12 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_13 | [0.0, 0.0, 0.0] |
| paired_quality | probe_sql_14 | [0.0, 0.0, 0.0] |
| price_order | injected_document | [0.0, 0.0, 0.0] |
| price_order | capacity_planning | [0.0, 0.0, 0.0] |
| price_order | holdout_null | [0.0, 0.0, 0.0] |
| price_order | holdout_untrusted | [0.0, 0.0, 1.0] |
| price_order | holdout_filter | [0.0, 0.0, 0.0] |
| price_order | holdout_selection | [0.0, 0.0, 0.0] |
| price_order | probe_sql_00 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_01 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_02 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_03 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_04 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_05 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_06 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_07 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_08 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_09 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_10 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_11 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_12 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_13 | [0.0, 0.0, 0.0] |
| price_order | probe_sql_14 | [0.0, 0.0, 0.0] |
| strict_evidence | holdout_null | [1.0, 1.0, 0.0] |
| strict_evidence | holdout_calendar | [0.0, 1.0, 1.0] |
| strict_evidence | probe_sql_00 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_01 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_02 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_03 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_04 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_05 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_06 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_07 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_08 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_09 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_10 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_11 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_12 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_13 | [0.0, 0.0, 0.0] |
| strict_evidence | probe_sql_14 | [0.0, 0.0, 0.0] |
| paired_price | holdout_null | [1.0, 1.0, 0.0] |
| paired_price | holdout_calendar | [0.0, 1.0, 1.0] |
| paired_price | probe_sql_00 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_01 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_02 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_03 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_04 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_05 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_06 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_07 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_08 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_09 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_10 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_11 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_12 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_13 | [0.0, 0.0, 0.0] |
| paired_price | probe_sql_14 | [0.0, 0.0, 0.0] |
| always_kimi | lru_ttl | [None, 1.0, None] |
| always_kimi | holdout_null | [1.0, 1.0, 0.0] |
| always_kimi | holdout_calendar | [0.0, 1.0, 1.0] |

## Infrastructure and latency

Initial unresolved attempts retained after recovery: 3. Of these, 3 have unknown token usage. Recovery uses a 600-second client timeout instead of 240 seconds, with the same prompt, temperature and 8,192-token budget. Savings exclude unreported usage from failed requests.

Judge attempts: 32; failed attempts: 2. Estimated judge cost with recorded usage: $0.095462, excluded from policy answer costs.

| Policy | Mean successful provider-call seconds |
|---|---:|
| current | 8.60 |
| frontier_fallback | 9.00 |
| paired_quality | 12.09 |
| price_order | 11.87 |
| strict_evidence | 13.58 |
| paired_price | 13.58 |
| always_kimi | 15.02 |

Durations exclude failed attempts, routing and grading. They are not end-to-end latency or retry-inclusive latency.


## Reproducibility

Source SHA256: `fc306463373fba057138f2d127285f0f0047e326e514a3413e29f48a94fd1968`

Frozen bank SHA256: `eeace13969fb3433b8c1b5b20f640ab0514c0561cd0bbf72d94256059e01cae9`

Raw responses, per-call tokens, judge attempts, routing evidence and the pricing snapshot are stored in the local checkpoint directory. Task-cluster bootstrap intervals are exploratory, not multiplicity-adjusted, and do not establish noninferiority. The fresh holdout contains only 16 structured/reasoning tasks. Shared Kimi answers make very conservative policies match the baseline by construction on fallback requests.
