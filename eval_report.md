# Eval Report: Router vs Always-Frontier Baseline

_--dry-run: no real provider calls. Cost column is a parameter-count proxy (real figure for local Ollama tiers, order-of-magnitude estimate for hosted tiers whose param counts aren't publicly disclosed), not real spend._

**Headline: 71% compute-proxy reduction, -3 point effectiveness delta vs always routing to the frontier tier.**

| Task | Router Tier | Router Compute Proxy (B params) | Router Score | Baseline Compute Proxy (B params) | Baseline Score |
|---|---|---|---|---|---|
| capital_france | cheap | 20.0 | 1.00 | 2000.0 | 1.00 |
| arithmetic | cheap | 20.0 | 1.00 | 2000.0 | 1.00 |
| unit_conversion | cheap | 20.0 | 1.00 | 2000.0 | 1.00 |
| quadratic_roots | medium | 200.0 | 1.00 | 2000.0 | 1.00 |
| code_fix | medium | 200.0 | 0.75 | 2000.0 | 0.89 |
| sql_query | medium | 200.0 | 0.65 | 2000.0 | 0.79 |
| multistep_planning | frontier | 2000.0 | 1.00 | 2000.0 | 1.00 |
| hard_math_proof | frontier | 2000.0 | 0.88 | 2000.0 | 0.88 |

**Totals** — Router: 4660.0, 90.9% effective. Frontier baseline: 16000.0, 94.4% effective.

-> **71% compute-proxy reduction, -3% effectiveness delta.**
