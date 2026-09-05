# NRP Model Characterization

| NRP name | Served id | Availability | Median latency |
|---|---|---|---|
| `gemma-small-e4b` | `google/gemma-4-E4B-it` | 3/3 | 234 ms |
| `gpt-oss` | `openai/gpt-oss-120b` | 3/3 | 282 ms |
| `minimax-m2` | `MiniMaxAI/MiniMax-M2.7` | 3/3 | 284 ms |
| `deepseek-v4-flash` | `deepseek-ai/DeepSeek-V4-Flash-Vision-Exp` | 3/3 | 287 ms |
| `qwen3-small` | `Qwen/Qwen3.8-27B` | 3/3 | 395 ms |
| `glm-5` | `Inferact/GLM-5.3-NVFP4` | 3/3 | 423 ms |
| `gemma4-small` | `google/gemma-4-12B-it-qat-w4a16-ct` | 3/3 | 453 ms |
| `qwen3` | `Qwen/Qwen3.8-Flash-Next-FP8` | 3/3 | 454 ms |
| `kimi` | `moonshotai/Kimi-K2.7-Code` | 3/3 | 505 ms |
| `gemma` | `google/gemma-4-31B-it-qat-w4a16-ct` | 3/3 | 511 ms |
| `gemma4-12b` | `google/gemma-4-12B-it-qat-w4a16-ct` | 3/3 | 2266 ms |
| `gemma-small` | `google/gemma-4-12B-it-qat-w4a16-ct` | 3/3 | 2268 ms |

## Distinct models (deduplicated by served id)

**10 distinct working models.**

- `Inferact/GLM-5.3-NVFP4`
- `MiniMaxAI/MiniMax-M2.7`
- `Qwen/Qwen3.8-27B`
- `Qwen/Qwen3.8-Flash-Next-FP8`
- `deepseek-ai/DeepSeek-V4-Flash-Vision-Exp`
- `google/gemma-4-12B-it-qat-w4a16-ct` (aliases: `gemma-small`, `gemma4-small`, `gemma4-12b`)
- `google/gemma-4-31B-it-qat-w4a16-ct`
- `google/gemma-4-E4B-it`
- `moonshotai/Kimi-K2.7-Code`
- `openai/gpt-oss-120b`

---

> The table above is **generated** by `python -m gatoway.characterize`. The
> analysis below it is appended **by hand** — a re-run overwrites this file
> and will drop it. Re-attach it, or move it into the design doc first.

Run: 2026-09-05, 3 rounds, 12 advertised chat models (`qwen3-embedding`
skipped as a non-chat model).

## Inventory changes since the NRP migration

- **`qwen3-4bit` is gone.** It is no longer advertised by `/v1/models` at
  all — 12 chat models are returned, not the 13 expected. Design §4.1 listed
  it as "failed to respond"; the reason is wrong, not just the row.
- **`gemma-small-e4b` works: 3/3.** Its single failure during the migration
  was transient. It is a distinct model (`google/gemma-4-E4B-it`) and the
  fastest entry in the table. Nine distinct working models becomes **ten**.
- Every model named as a rung in design §4.2 returned 3/3. No rung is
  dropped for unavailability.

## Latency vs parameter ordering

**The measurement does not discriminate, so no ordering verdict is given.**

Design §4.4 proposed measured latency as the observed second signal against
published parameter counts, to catch MoE models whose total and active
params disagree. This run cannot serve that purpose:

- A **250x** parameter range collapses into a **2x** latency band —
  `gemma-small-e4b` (~4B) at 234 ms through `kimi` (1T) at 505 ms.
- The ordering inside that band contradicts params outright: `gemma` (31B)
  at 511 ms is *slower* than `kimi` (1T) at 505 ms.
- One served id, `google/gemma-4-12B-it-qat-w4a16-ct`, reached all three
  aliases. Two of them measured ~2267 ms and the third 453 ms — same
  weights, same endpoint. Re-probing all three minutes later returned
  344–619 ms across nine calls. The 2266/2268 ms medians are not a property
  of the model. The cause is not established and is left open.

**Why**: `PROBE_MAX_TOKENS = 5`. Five output tokens are dominated by fixed
request and scheduling overhead, so model size barely enters the number.

**Upgrade path**: longer generations scored as tokens/sec, not more rounds.
Additional rounds of a 5-token probe cannot separate 4B from 1T, because the
quantity being measured is mostly not generation.

Until such a probe exists, published parameter count is the *only* signal
behind the cost model, and §4.4's mitigation is unproven rather than
validated.
