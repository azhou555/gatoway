# MVP Task Breakdown — Cost-Aware LLM Gateway

Scope: smallest system that proves the north-star story (route to cheapest
tier via embedding similarity, session-aware threshold shift, fallback on
failure, batch feedback loop, eval harness with a cost/effectiveness report).

Cut for MVP (add later, not blocking the demo):
- OpenTelemetry/Prometheus/Grafana — plain structured logs instead.
- Ollama local tier — stub adapter only, not wired into router by default.
- TF-IDF/ML keyword extraction — naive noun-phrase/keyword overlap heuristic.
- Redis for session state — start in Postgres/in-process; swap to Redis only
  if turn latency becomes a real problem.

Stack: Python, FastAPI, `litellm` for provider calls (spec explicitly says
reuse rather than rebuild provider/streaming handling), Postgres + pgvector
via `asyncpg`/SQLAlchemy, `sentence-transformers` or OpenAI embeddings for
vectors (pick whichever needs no paid key for local dev — prefer a local
`sentence-transformers` model so the demo runs offline).

## Subtasks

### 1. Infra & Schema (foundation — do first, others build against it)
- `docker-compose.yml`: postgres (pgvector/pgvector image), no separate redis
  for MVP.
- `schema.sql`: `spend_ledger`, `sessions`, `decision_history` tables + the
  ivfflat index, exactly as in SPEC.md §4 (adjust `VECTOR(n)` to match the
  chosen embedding model's dimension).
- `pyproject.toml`/`requirements.txt`, `.env.example`, project skeleton
  (`gatoway/` package, `Makefile` or `just` targets for `up`/`migrate`/`test`).
- A `db.py` with a connection pool and a `migrate` script that applies
  `schema.sql`.

### 2. Provider Adapters + Circuit Breaker
- Thin wrapper around `litellm.completion` for tiers: cheap / medium
  (Sonnet) / frontier, mapped to real model IDs via config.
- Circuit breaker per (tier, provider): 3 consecutive failures → mark
  unhealthy → 60s cooldown → retry, per SPEC.md §5. In-process state is fine
  for MVP (single gateway instance).
- Classifier-failure path: on embedding/router error, default straight to
  Sonnet tier, single request, no breaker involvement.
- Unit tests with a fake/mocked provider to exercise the failure → retry →
  cooldown state machine.

### 3. Router/Classifier + Session Tracker
- Embedding function (local `sentence-transformers`, e.g. `all-MiniLM-L6-v2`)
  and a pgvector nearest-neighbor query (cosine) against `decision_history`.
- Confidence floor: below threshold similarity → treat as no-match →
  fallback tier per SPEC.md §4 notes.
- Session tracker: keyword extraction (simple overlap heuristic) from first
  request, session boundary detection, `current_threshold` shifting as
  `turn_count` grows relative to `expected_turn_count` (SPEC.md §6).
- Pure-logic module, testable without the HTTP layer.

### 4. Gateway API (integration — depends on 1, 2, 3)
- FastAPI app, OpenAI-compatible `POST /v1/chat/completions`.
- Wires session tracker → router → circuit breaker → provider adapter →
  writes a `decision_history` row (embeddings + model_id + confidence).
- Structured request/decision logging (stand-in for the OTel spans cut from
  MVP scope).

### 5. Batch Feedback Job + Eval Harness + Seed Data (depends on 1, 3)
- Seed script: writes a small train-split bank of synthetic
  request/response pairs + embeddings into `decision_history` before any
  live traffic (cold-start, per SPEC.md §8).
- Batch job: at session end, compute `quality_score`, write session
  embedding back to the bank **only for train-split sessions**, update
  `spend_ledger.avg_session_difficulty`.
- Eval harness: 5–10 hand-written benchmark tasks (mix of exact-match and a
  cheap rubric/LLM-judge stub), held-out (never written back), run against
  the live router vs an "always frontier" baseline, output the headline
  effectiveness/cost report (e.g. "-63% cost, -2% effectiveness").

## Execution plan
Wave 1 (parallel, independent): 1, 2, 3.
Wave 2 (sequential, integrates prior wave): 4, then 5.
