# Eval Report: Router vs Always-Highest-Rung Baseline

_Real calls against NRP-hosted models._ _Cost is a parameter-count proxy, not real spend: NRP has no per-token billing, so each model is priced at its published parameter count in billions per 1M tokens. Only relative ordering is meaningful._

_Scoring: exact match for factual tasks; constrained Python/SQLite fixture execution for code and SQL; heuristic judging only for the two open-ended tasks._

_Session evaluation: 8 consecutive turns per run; expected turn count 3; thresholds therefore rise on later turns._

_Routing: DB-backed pgvector `decision_history` lookup (24 rows)._

_Generation controls: temperature 0, maximum 512 tokens, 60s timeout, 1 timeout retry._

**Headline across 3 runs: 82.7% (81.9%–83.2%) cost reduction, -5.2 pt (-12.5 pt to +1.6 pt) effectiveness delta vs always-highest-rung.**

**Stability gate: FAIL** — unstable scores: router/code_fix.

| Turn | Task | Threshold | Router Tier(s) | Router Cost Proxy (¢) mean (range) | Router Score mean (range) | Baseline Cost Proxy (¢) mean (range) | Baseline Score mean (range) |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | capital_france | 0.50 | gemma-small | 0.000 | 1.00 | 0.050 (0.041–0.069) | 1.00 |
| 2 | arithmetic | 0.50 | gpt-oss | 0.016 | 1.00 | 0.073 (0.070–0.074) | 1.00 |
| 3 | unit_conversion | 0.50 | gpt-oss | 0.027 (0.026–0.028) | 1.00 | 0.097 (0.072–0.147) | 1.00 |
| 4 | quadratic_roots | 0.63 | gpt-oss | 0.037 | 1.00 | 0.157 (0.145–0.168) | 1.00 |
| 5 | code_fix | 0.77 | gpt-oss | 0.072 | 0.67 (0.00–1.00) | 0.262 (0.257–0.268) | 1.00 |
| 6 | sql_query | 0.90 | gpt-oss | 0.071 | 1.00 | 0.457 (0.370–0.536) | 1.00 |
| 7 | multistep_planning | 0.90 | gpt-oss | 0.072 | 0.79 (0.75–0.88) | 0.542 | 0.75 (0.62–1.00) |
| 8 | hard_math_proof | 0.90 | gpt-oss | 0.071 | 0.88 (0.88–0.88) | 0.486 (0.466–0.499) | 1.00 (1.00–1.00) |

**Session totals (mean and range)** — Router: 0.367 (0.366–0.368), 91.7% (82.8%–96.9%) effective. Highest-rung baseline: 2.124 (2.027–2.185), 96.9% (95.3%–100.0%) effective.
