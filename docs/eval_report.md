# Eval Report: Router vs Always-Frontier Baseline

_Real calls against NRP-hosted models._ _Cost is a parameter-count proxy, not real spend: NRP has no per-token billing, so each model is priced at its published parameter count in billions per 1M tokens. Only relative ordering is meaningful._

_Scoring: exact match for factual tasks; constrained Python/SQLite fixture execution for code and SQL; heuristic judging only for the two open-ended tasks._

_Session evaluation: 8 consecutive turns per run; expected turn count 3; thresholds therefore rise on later turns._

_Routing: DB-backed pgvector `decision_history` lookup (24 rows)._

_Generation controls: temperature 0, maximum 512 tokens, 60s timeout, 1 timeout retry._

**Headline across 3 runs: 40.1% (36.6%–42.7%) cost reduction, -1.0 pt (-3.1 pt to +0.0 pt) effectiveness delta vs always-frontier.**

**Stability gate: PASS** — all six exact/execution tasks were identical across runs.

| Turn | Task | Threshold | Router Tier(s) | Router Cost Proxy (¢) mean (range) | Router Score mean (range) | Baseline Cost Proxy (¢) mean (range) | Baseline Score mean (range) |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | capital_france | 0.50 | cheap | 0.000 | 1.00 | 0.016 | 1.00 |
| 2 | arithmetic | 0.50 | cheap | 0.000 | 1.00 | 0.022 | 1.00 |
| 3 | unit_conversion | 0.50 | cheap | 0.002 | 1.00 | 0.023 (0.022–0.023) | 1.00 |
| 4 | quadratic_roots | 0.63 | medium | 0.005 | 1.00 | 0.035 (0.032–0.037) | 1.00 |
| 5 | code_fix | 0.77 | medium | 0.012 (0.012–0.013) | 1.00 | 0.066 (0.060–0.075) | 1.00 |
| 6 | sql_query | 0.90 | medium | 0.009 (0.009–0.010) | 1.00 | 0.046 (0.043–0.052) | 1.00 |
| 7 | multistep_planning | 0.90 | frontier | 0.105 | 0.79 (0.62–0.88) | 0.105 | 0.88 (0.88–0.88) |
| 8 | hard_math_proof | 0.90 | frontier | 0.104 | 0.88 (0.88–0.88) | 0.084 (0.074–0.104) | 0.88 (0.88–0.88) |

**Session totals (mean and range)** — Router: 0.238 (0.237–0.238), 95.8% (93.8%–96.9%) effective. Frontier baseline: 0.397 (0.375–0.413), 96.9% (96.9%–96.9%) effective.
