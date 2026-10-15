# OpenRouter price comparison

The primary monetary comparison now uses published OpenRouter input/output rates multiplied by recorded NRP token usage. Parameter-count proxy results are historical diagnostics, not monetary savings.

**Result: 25.5% estimated savings on 54 matched pairs out of 96. Full-suite savings are unavailable.** Routed answers in the matched subset cost $0.053461 versus $0.071749 for the same baseline tasks. The full 96-answer baseline costs $0.146269; comparing that total with the partial router subtotal would be misleading.

The other 42 routed answers used Gemma 4 12B, which has no corresponding listing in the captured catalog. Gemma 3 12B and Gemma 4 31B are different models and are not substituted. This missingness is systematic, so the 54-pair result must not be extrapolated to the full suite.

The original quality results remain 89.3% routed versus 92.7% baseline across all tasks, with a failed stability gate. Repricing does not establish accuracy-preserving savings.

## Published rates

USD per million tokens, captured 2026-10-04T06:02:58.323436+00:00.

| NRP alias | OpenRouter model | Input | Output |
|---|---|---:|---:|
| openai/gemma-small | Unavailable | — | — |
| openai/qwen3-small | qwen/qwen3.8-27b | 0.42 | 3 |
| openai/gpt-oss | openai/gpt-oss-120b | 0.037 | 0.17 |
| openai/qwen3 | qwen/qwen3.8-flash | 0.15 | 0.47 |
| openai/gemma | google/gemma-4-31b-it | 0.09 | 0.34 |
| openai/minimax-m2 | minimax/minimax-m2.7 | 0.21 | 0.84 |
| openai/deepseek-v4-flash | deepseek/deepseek-v4-flash-vision-exp | 0.2156 | 0.6468 |
| openai/glm-5 | z-ai/glm-5.3 | 1.4 | 4.4 |
| openai/kimi | moonshotai/kimi-k2.7-code | 0.6712 | 3.35 |

Mappings follow the [NRP model documentation](https://nrp.ai/documentation/userdocs/ai/llm-managed/models/); prices come from the [OpenRouter catalog](https://openrouter.ai/api/v1/models). These are corresponding base-model estimates: NRP quantization and serving configuration can differ, and the saved responses record aliases rather than immutable checkpoint revisions. Catalog pricing describes the top provider, not a guaranteed invoice for any provider ([API documentation](https://openrouter.ai/docs/guides/overview/models)).

Assumptions: uncached text input and reported completion tokens, including reasoning where included in completion usage. Excludes judge calls, embeddings, fees, infrastructure and failed attempts without token usage. This is an October 4 price counterfactual, not historical billed spend. NRP execution and OpenRouter execution need not produce identical usage or quality.

The routing policy still orders models by parameter count. This experiment changes accounting only; a price-aware routing policy requires a separate evaluation. In particular, GPT-OSS is cheaper than Qwen small, and GLM costs more per output token than Kimi. The old cost_cents fields in the gateway and historical evaluators remain legacy proxy fields; use this explicit USD report for monetary comparisons.

## Reproduce without new inference

```sh
python -m gatoway.reprice_eval \
  --snapshot benchmarks/pricing/openrouter_20261004.json \
  --checkpoints artifacts/expanded_eval_v2_20261003/eval_partial_{1,2,3}.json \
  --output /tmp/openrouter_comparison.json
```

The output path must be new. The tool makes no network calls, keeps missing prices null, compares identical task/run pairs, and records snapshot and checkpoint hashes. Raw checkpoints remain local ignored artifacts. The compact [price snapshot](../benchmarks/pricing/openrouter_20261004.json) and [result summary](../benchmarks/pricing/expanded_20261004_summary.json) are versionable. Refresh prices and verify NRP aliases before future runs; never silently reuse these rates as current prices.
