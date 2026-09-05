# Eval Report: Router vs Always-Frontier Baseline

_Real calls against NRP-hosted models._ _Cost is a parameter-count proxy, not real spend: NRP has no per-token billing, so each model is priced at its published parameter count in billions per 1M tokens. Only relative ordering is meaningful._

**Headline: 33% cost reduction, -6 point effectiveness delta vs always routing to the frontier tier.**

| Task | Router Tier | Router Cost Proxy (¢) | Router Score | Baseline Cost Proxy (¢) | Baseline Score |
|---|---|---|---|---|---|
| capital_france | cheap | 0.000 | 1.00 | 0.017 | 1.00 |
| arithmetic | cheap | 0.000 | 1.00 | 0.023 | 1.00 |
| unit_conversion | cheap | 0.002 | 1.00 | 0.024 | 1.00 |
| quadratic_roots | cheap | 0.006 | 1.00 | 0.032 | 1.00 |
| code_fix | medium | 0.009 | 0.53 | 0.210 | 0.67 |
| sql_query | medium | 0.011 | 0.50 | 0.079 | 1.00 |
| multistep_planning | frontier | 0.314 | 1.00 | 0.197 | 1.00 |
| hard_math_proof | frontier | 0.099 | 1.00 | 0.071 | 0.88 |

**Totals** — Router: 0.441, 87.9% effective. Frontier baseline: 0.654, 94.3% effective.

-> **33% cost reduction, -6% effectiveness delta.**
