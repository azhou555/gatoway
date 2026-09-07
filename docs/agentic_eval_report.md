# Agentic Coding Eval Report

_Mode: live NRP model calls; routing: DB-backed pgvector; 3 run(s). Accepted patches were executed in a network-disabled, resource-limited Docker container. Grader image: `python:3.13-slim (sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f)`._

**Router: solved 9/9 (100%); first-pass 9/9 (100%); mean turns 1.00; tier switches 0; tokens 6,690; provider latency 71.4s.**

**Production readiness gate: PASS — every task passed at least 2/3 with no exhausted tier.**

**Always-frontier baseline: solved 9/9 (100%); first-pass 8/9 (89%); mean turns 1.11; tier switches 0; tokens 7,882; provider latency 149.9s.**

**Baseline readiness gate: PASS — every task passed at least 2/3 with no exhausted tier.**

**Router vs baseline: 87.2% lower compute/cost proxy and 52.4% lower provider latency.**

| Run | Path | Task | Result | Turns | Tier path | Model path | Tokens | Provider latency | Compute/cost proxy | Failure |
|---:|---|---|---|---:|---|---|---:|---:|---:|---|
| 1 | router | dependency_planner | PASS | 1 | medium | qwen3-small | 805 | 6.1s | 0.022 | — |
| 1 | router | ttl_cache | PASS | 1 | medium | qwen3-small | 799 | 9.6s | 0.022 | — |
| 1 | router | webhook_idempotency | PASS | 1 | medium | qwen3-small | 645 | 4.9s | 0.017 | — |
| 1 | always_frontier | dependency_planner | PASS | 1 | frontier | qwen3 | 896 | 20.2s | 0.161 | — |
| 1 | always_frontier | ttl_cache | PASS | 1 | frontier | qwen3 | 760 | 8.1s | 0.137 | — |
| 1 | always_frontier | webhook_idempotency | PASS | 1 | frontier | qwen3 | 724 | 15.4s | 0.130 | — |
| 2 | router | dependency_planner | PASS | 1 | medium | qwen3-small | 818 | 7.2s | 0.022 | — |
| 2 | router | ttl_cache | PASS | 1 | medium | qwen3-small | 794 | 5.3s | 0.021 | — |
| 2 | router | webhook_idempotency | PASS | 1 | medium | qwen3-small | 584 | 14.5s | 0.016 | — |
| 2 | always_frontier | dependency_planner | PASS | 2 | frontier → frontier | qwen3 → qwen3 | 1,646 | 30.8s | 0.296 | — |
| 2 | always_frontier | ttl_cache | PASS | 1 | frontier | qwen3 | 765 | 12.6s | 0.138 | — |
| 2 | always_frontier | webhook_idempotency | PASS | 1 | frontier | qwen3 | 716 | 13.4s | 0.129 | — |
| 3 | router | dependency_planner | PASS | 1 | medium | qwen3-small | 862 | 8.1s | 0.023 | — |
| 3 | router | ttl_cache | PASS | 1 | medium | qwen3-small | 799 | 12.4s | 0.022 | — |
| 3 | router | webhook_idempotency | PASS | 1 | medium | qwen3-small | 584 | 3.3s | 0.016 | — |
| 3 | always_frontier | dependency_planner | PASS | 1 | frontier | qwen3 | 886 | 24.8s | 0.159 | — |
| 3 | always_frontier | ttl_cache | PASS | 1 | frontier | qwen3 | 765 | 10.1s | 0.138 | — |
| 3 | always_frontier | webhook_idempotency | PASS | 1 | frontier | qwen3 | 724 | 14.6s | 0.130 | — |

Full per-turn prompts, responses, finish reasons, provider failures, and grader observations: `artifacts/agentic_eval/20260907T162044Z`.

This is a repeated live model-quality measurement. Timed-out calls that returned no usage metadata contribute to provider latency but not to the token or compute/cost proxy totals.
