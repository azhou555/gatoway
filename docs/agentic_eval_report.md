# Agentic Coding Eval Report

_Mode: live NRP model calls; routing: DB-backed pgvector; 3 run(s). Accepted patches were executed in a network-disabled, resource-limited Docker container. Grader image: `python:3.13-slim (sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f)`._

**Solved: 3/9 (33%); first-pass: 0/9 (0%); mean turns: 2.67; tier switches: 3; tokens: 103,038; provider latency: 1892.8s.**

**Production readiness gate: FAIL — dependency_planner passed 0/3; webhook_idempotency passed 0/3; 2 attempt(s) exhausted both tier models.**

| Run | Task | Result | Turns | Tier path | Model path | Tokens | Provider latency | Compute/cost proxy | Failure |
|---:|---|---|---:|---|---|---:|---:|---:|---|
| 1 | dependency_planner | FAIL | 3 | medium → medium → medium | qwen3-small → qwen3-small → qwen3-small | 15,995 | 103.9s | 0.432 | Held-out tests failed |
| 1 | ttl_cache | PASS | 2 | medium → frontier | qwen3-small → qwen3 | 8,792 | 101.1s | 1.155 | — |
| 1 | webhook_idempotency | FAIL | 3 | medium → medium → medium | qwen3-small → gemma → provider-error/medium | 8,146 | 510.1s | 0.242 | Provider failure |
| 2 | dependency_planner | FAIL | 3 | medium → medium → medium | qwen3-small → qwen3-small → qwen3-small | 15,976 | 98.3s | 0.431 | No applicable diff |
| 2 | ttl_cache | PASS | 2 | medium → frontier | qwen3-small → qwen3 | 8,274 | 59.4s | 1.062 | — |
| 2 | webhook_idempotency | FAIL | 3 | medium → medium → medium | qwen3-small → qwen3-small → qwen3-small | 15,952 | 90.0s | 0.431 | No applicable diff |
| 3 | dependency_planner | FAIL | 3 | medium → medium → medium | qwen3-small → gemma → gemma | 13,408 | 477.5s | 0.405 | No applicable diff |
| 3 | ttl_cache | PASS | 2 | medium → frontier | qwen3-small → qwen3 | 8,266 | 65.6s | 1.060 | — |
| 3 | webhook_idempotency | FAIL | 3 | medium → medium → medium | qwen3-small → provider-error/medium → qwen3-small | 8,229 | 387.0s | 0.222 | No applicable diff |

This is a repeated live model-quality measurement. Timed-out calls that returned no usage metadata contribute to provider latency but not to the token or compute/cost proxy totals.
