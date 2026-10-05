# Policy screening results

**Status: 342/342 unique task/model/repetition outcomes scored.**

[Protocol and limitations](policy_comparison.md). Prices include the unverified Gemma rate assumption. All policies share the same generation controls and matched answers. No production policy was changed.

The best conservative candidates are **strict_evidence** and **paired_price**:
26.5% estimated savings with 98.26% mean quality versus Kimi's 97.68%.
Their decisions are identical on this set, so this is one observed routing
pattern, not two independent confirmations. They route 129/144 requests to
Kimi, including every fresh holdout request. The fresh holdout therefore
shows preserved baseline behavior with **zero savings**, not evidence of
successful generalization to cheaper models.

Paired quality also avoids an observed aggregate loss, but saves only 13.2%.
Fallback-only and price-only changes leave substantial quality regressions.
Price ordering is useful accounting, but insufficient as a quality policy.

The conservative mean-quality gain comes from better partial scores on the
LRU task; it is not broad superiority over Kimi. Strict routing and Kimi both
fully pass 128/132 objective answers and still have unstable tasks. No policy
is promoted. The next validation should target the few proposed downgrades
with fresh coding tasks and repeated outcomes, while improving coverage of
structured/reasoning training examples separately from the holdout.

All estimates exclude unknown usage from 14 failed initial attempts and use
the assumed Gemma rate. The larger answer budget changes this experiment's
baseline, so results should not be compared directly with the previous run.

## All

| Policy | Scored pairs | Quality | Delta vs Kimi (points) | Exploratory 95% interval | Estimated USD | Savings | Length finishes |
|---|---:|---:|---:|---|---:|---:|---:|
| current | 144 (0 missing) | 83.61% | -14.07 | [-24.31, -4.44] | $0.166112 | 32.6% | 3 |
| frontier_fallback | 144 (0 missing) | 89.17% | -8.51 | [-17.12, -1.15] | $0.198004 | 19.7% | 3 |
| paired_quality | 144 (0 missing) | 98.36% | +0.68 | [+0.00, +1.93] | $0.213957 | 13.2% | 0 |
| price_order | 144 (0 missing) | 88.08% | -9.60 | [-18.73, -1.75] | $0.068162 | 72.3% | 0 |
| strict_evidence | 144 (0 missing) | 98.26% | +0.58 | [+0.00, +1.74] | $0.181231 | 26.5% | 0 |
| paired_price | 144 (0 missing) | 98.26% | +0.58 | [+0.00, +1.74] | $0.181231 | 26.5% | 0 |
| always_kimi | 144 (0 missing) | 97.68% | +0.00 | [+0.00, +0.00] | $0.246442 | 0.0% | 1 |

## Existing

| Policy | Scored pairs | Quality | Delta vs Kimi (points) | Exploratory 95% interval | Estimated USD | Savings | Length finishes |
|---|---:|---:|---:|---|---:|---:|---:|
| current | 96 (0 missing) | 90.00% | -8.60 | [-19.17, +0.77] | $0.164473 | 27.0% | 3 |
| frontier_fallback | 96 (0 missing) | 93.12% | -5.48 | [-15.27, +1.96] | $0.180680 | 19.8% | 3 |
| paired_quality | 96 (0 missing) | 99.62% | +1.02 | [+0.00, +2.90] | $0.192006 | 14.8% | 0 |
| price_order | 96 (0 missing) | 93.58% | -5.02 | [-15.00, +1.94] | $0.066505 | 70.5% | 0 |
| strict_evidence | 96 (0 missing) | 99.47% | +0.87 | [+0.00, +2.60] | $0.160191 | 28.9% | 0 |
| paired_price | 96 (0 missing) | 99.47% | +0.87 | [+0.00, +2.60] | $0.160191 | 28.9% | 0 |
| always_kimi | 96 (0 missing) | 98.60% | +0.00 | [+0.00, +0.00] | $0.225403 | 0.0% | 1 |

## Holdout

| Policy | Scored pairs | Quality | Delta vs Kimi (points) | Exploratory 95% interval | Estimated USD | Savings | Length finishes |
|---|---:|---:|---:|---|---:|---:|---:|
| current | 48 (0 missing) | 70.83% | -25.00 | [-45.83, -6.25] | $0.001638 | 92.2% | 0 |
| frontier_fallback | 48 (0 missing) | 81.25% | -14.58 | [-31.25, +0.00] | $0.017324 | 17.7% | 0 |
| paired_quality | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | $0.021951 | -4.3% | 0 |
| price_order | 48 (0 missing) | 77.08% | -18.75 | [-37.50, -4.17] | $0.001658 | 92.1% | 0 |
| strict_evidence | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | $0.021039 | 0.0% | 0 |
| paired_price | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | $0.021039 | 0.0% | 0 |
| always_kimi | 48 (0 missing) | 95.83% | +0.00 | [+0.00, +0.00] | $0.021039 | 0.0% | 0 |

## Category quality deltas

Points relative to Kimi; negative means worse.

| Policy | coding | holdout_reasoning | holdout_structured | original | reasoning | structured |
|---|---:|---:|---:|---:|---:|---:|
| current | -9.40 | -25.00 | -25.00 | +0.00 | -12.50 | -12.50 |
| frontier_fallback | -9.40 | -25.00 | -4.17 | +0.00 | -12.50 | +0.00 |
| paired_quality | +4.07 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |
| price_order | +4.90 | -12.50 | -25.00 | +0.00 | -12.50 | -12.50 |
| strict_evidence | +3.47 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |
| paired_price | +3.47 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |
| always_kimi | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 |

## Routing mix

| Policy | Model counts across task/repetitions |
|---|---|
| current | {'gemma-small': 51, 'glm-5': 3, 'qwen3-small': 12, 'gpt-oss': 78} |
| frontier_fallback | {'gemma-small': 51, 'glm-5': 3, 'qwen3-small': 12, 'gpt-oss': 6, 'kimi': 72} |
| paired_quality | {'kimi': 96, 'gemma-small': 18, 'glm-5': 9, 'qwen3-small': 12, 'gpt-oss': 9} |
| price_order | {'gpt-oss': 123, 'glm-5': 3, 'gemma-small': 15, 'qwen3-small': 3} |
| strict_evidence | {'kimi': 129, 'glm-5': 3, 'gemma-small': 3, 'gpt-oss': 9} |
| paired_price | {'kimi': 129, 'glm-5': 3, 'gemma-small': 3, 'gpt-oss': 9} |
| always_kimi | {'kimi': 144} |

## Objective full passes and repeatability

| Policy | Full passes | Scored objective answers | Unstable task IDs |
|---|---:|---:|---|
| current | 112 | 132 | holdout_filter |
| frontier_fallback | 120 | 132 | none |
| paired_quality | 129 | 132 | lru_ttl, holdout_null |
| price_order | 114 | 132 | lru_ttl, holdout_filter |
| strict_evidence | 128 | 132 | grid_shortest_path, lru_ttl, holdout_null |
| paired_price | 128 | 132 | grid_shortest_path, lru_ttl, holdout_null |
| always_kimi | 128 | 132 | grid_shortest_path, lru_ttl, holdout_null |

## Objective task failures and repeatability

Full pass means score 1.0. A stable failure is still a failure. Open-ended rubric tasks are excluded from this table.

| Policy | Task | Scores by repetition |
|---|---|---|
| current | injected_document | [0.0, 0.0, 0.0] |
| current | capacity_planning | [0.0, 0.0, 0.0] |
| current | holdout_null | [0.0, 0.0, 0.0] |
| current | holdout_untrusted | [0.0, 0.0, 0.0] |
| current | holdout_filter | [0.0, 0.0, 1.0] |
| current | holdout_selection | [0.0, 0.0, 0.0] |
| current | holdout_calendar | [0.0, 0.0, 0.0] |
| frontier_fallback | capacity_planning | [0.0, 0.0, 0.0] |
| frontier_fallback | holdout_null | [0.0, 0.0, 0.0] |
| frontier_fallback | holdout_selection | [0.0, 0.0, 0.0] |
| frontier_fallback | holdout_calendar | [0.0, 0.0, 0.0] |
| paired_quality | lru_ttl | [1.0, 0.8333333333333334, 1.0] |
| paired_quality | holdout_null | [0.0, 0.0, 1.0] |
| price_order | lru_ttl | [1.0, 0.8333333333333334, 1.0] |
| price_order | injected_document | [0.0, 0.0, 0.0] |
| price_order | capacity_planning | [0.0, 0.0, 0.0] |
| price_order | holdout_null | [0.0, 0.0, 0.0] |
| price_order | holdout_untrusted | [0.0, 0.0, 0.0] |
| price_order | holdout_filter | [0.0, 0.0, 1.0] |
| price_order | holdout_selection | [0.0, 0.0, 0.0] |
| strict_evidence | grid_shortest_path | [1.0, 0.8571428571428571, 1.0] |
| strict_evidence | lru_ttl | [1.0, 0.8333333333333334, 1.0] |
| strict_evidence | holdout_null | [0.0, 0.0, 1.0] |
| paired_price | grid_shortest_path | [1.0, 0.8571428571428571, 1.0] |
| paired_price | lru_ttl | [1.0, 0.8333333333333334, 1.0] |
| paired_price | holdout_null | [0.0, 0.0, 1.0] |
| always_kimi | grid_shortest_path | [1.0, 0.8571428571428571, 1.0] |
| always_kimi | lru_ttl | [1.0, 0.0, 1.0] |
| always_kimi | holdout_null | [0.0, 0.0, 1.0] |

## Infrastructure and latency

Initial unresolved attempts retained after recovery: 14. Of these, 14 have unknown token usage. Recovery uses a 600-second client timeout instead of 240 seconds, with the same prompt, temperature and 8,192-token budget. Savings exclude unreported usage from failed requests.

Judge attempts: 31; failed attempts: 1. Estimated judge cost with recorded usage: $0.090198, excluded from policy answer costs.

| Policy | Mean successful provider-call seconds |
|---|---:|
| current | 9.57 |
| frontier_fallback | 12.05 |
| paired_quality | 19.65 |
| price_order | 11.43 |
| strict_evidence | 21.48 |
| paired_price | 21.48 |
| always_kimi | 29.58 |

Durations exclude failed attempts, routing and grading. They are not end-to-end latency or retry-inclusive latency.


## Reproducibility

Source SHA256: `d82385b09d46652712eb41d1efaf52b7be567e2e13e94cdf809a132210c357bf`

Frozen bank SHA256: `eeace13969fb3433b8c1b5b20f640ab0514c0561cd0bbf72d94256059e01cae9`

Raw responses, per-call tokens, judge attempts, routing evidence and the pricing snapshot are stored in the local checkpoint directory. Task-cluster bootstrap intervals are exploratory, not multiplicity-adjusted, and do not establish noninferiority. The fresh holdout contains only 16 structured/reasoning tasks. Shared Kimi answers make very conservative policies match the baseline by construction on fallback requests.
