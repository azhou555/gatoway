# Eval Report: Router vs Always-Highest-Rung Baseline

_Real calls against NRP-hosted models._ _Cost is a parameter-count proxy, not real spend: NRP has no per-token billing, so each model is priced at its published parameter count in billions per 1M tokens. Only relative ordering is meaningful._

_Scoring: exact match for factual tasks; constrained Python/SQLite fixture execution for code and SQL; heuristic judging only for the two open-ended tasks._

_Session evaluation: 8 consecutive turns per run; expected turn count 3; thresholds therefore rise on later turns._

_Routing: DB-backed pgvector `decision_history` lookup (24 rows)._

_Generation controls: temperature 0, maximum 512 tokens, 60s timeout, 1 timeout retry._

**Headline across 3 runs: 40.0% (38.9%–40.8%) cost reduction, -16.7 pt (-26.6 pt to -7.8 pt) effectiveness delta vs always-highest-rung.**

**Stability gate: FAIL** — unstable scores: router/sql_query.

| Turn | Task | Threshold | Router Tier(s) | Router Cost Proxy (¢) mean (range) | Router Score mean (range) | Baseline Cost Proxy (¢) mean (range) | Baseline Score mean (range) |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | capital_france | 0.50 | gemma-small | 0.000 | 1.00 | 0.041 (0.039–0.042) | 1.00 |
| 2 | arithmetic | 0.50 | gpt-oss | 0.016 | 1.00 | 0.074 | 1.00 |
| 3 | unit_conversion | 0.50 | qwen3-small | 0.003 | 1.00 | 0.074 (0.072–0.079) | 1.00 |
| 4 | quadratic_roots | 0.63 | gpt-oss | 0.032 (0.030–0.037) | 1.00 | 0.164 (0.157–0.179) | 1.00 |
| 5 | code_fix | 0.77 | minimax-m2 | 0.131 | 0.00 | 0.247 (0.232–0.267) | 1.00 |
| 6 | sql_query | 0.90 | minimax-m2 | 0.130 | 0.67 (0.00–1.00) | 0.444 (0.409–0.472) | 1.00 |
| 7 | multistep_planning | 0.90 | kimi | 0.542 | 0.67 (0.50–1.00) | 0.542 | 0.67 (0.62–0.75) |
| 8 | hard_math_proof | 0.90 | glm-5 | 0.404 | 1.00 (1.00–1.00) | 0.512 (0.487–0.531) | 1.00 (1.00–1.00) |

**Session totals (mean and range)** — Router: 1.259 (1.256–1.264), 79.2% (68.8%–87.5%) effective. Highest-rung baseline: 2.099 (2.068–2.124), 95.8% (95.3%–96.9%) effective.
