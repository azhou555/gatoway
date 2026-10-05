# gatoway

Cost-aware LLM gateway (MVP). Routes each request to the cheapest model rung
likely to produce an acceptable result, using embedding-similarity matching
against a growing bank of past requests plus session-level difficulty
signals — instead of static per-request rules.

Full architecture: `docs/spec.md`. Subtask breakdown: `docs/tasks.md`.
Design docs and implementation plans live in `docs/specs/` and `docs/plans/`.

## Status

MVP is implemented end-to-end and passing the full test suite: gateway API,
evidence-based eight-rung router (top-k embedding similarity + session-aware
effectiveness bar), circuit breaker
with provider fallback, batch feedback job, seed data, and an eval harness
that produces the cost/effectiveness report below.

Cut from v0.1 (see `docs/tasks.md` for the full list and why): OpenTelemetry /
Prometheus / Grafana, Redis-backed session state, an Ollama local rung,
ML-based keyword
extraction. Live eval now uses a rubric LLM judge; dry runs retain the heuristic stub.

## Getting started

```bash
# 1. Start Postgres (pgvector), add your NRP API key to .env
cp .env.example .env   # then set NRP_API_KEY — https://nrp.ai/llmtoken/
docker compose up -d

# 2. Install deps
pip install -e ".[dev]"

# 3. Run the schema migration
python -m gatoway.db migrate

# 4. Seed the embedding bank (cold start — see SPEC.md §8)
python -m gatoway.seed

# 4b. (optional) Grow the bank with your own difficulty labels, no LLM needed
python -m gatoway.label_seed

# 5. Run tests
pytest

# 5b. Check gateway-added latency against SPEC.md §9's <=100ms budget
python -m gatoway.bench_latency

# 6. Run the gateway API
uvicorn gatoway.app:app --reload
# or: python -m gatoway.main
```

### Model ladder

All rungs are NRP-hosted open-weights models served from a single
OpenAI-compatible endpoint (`https://ellm.nrp-nautilus.io/v1`). The router
selects the cheapest rung with at least two effective observations among up to
five nearest scored neighbors per configured model. If no rung clears that
evidence bar, it explicitly uses `gpt-oss`. Every rung has a context-aware
provider fallback:

| Rung | Primary | Params | Context | Fallback |
|---:|---|---:|---:|---|
| 0 | `gemma-small` | 12B | 262K | `qwen3-small` |
| 1 | `qwen3-small` | 27B | 1M | `gemma` (31B) |
| 2 | `gpt-oss` | 120B | 131K | `qwen3` |
| 3 | `qwen3` | 180B | 1M | `gpt-oss` |
| 4 | `minimax-m2` | 230B | 205K | `deepseek-v4-flash` |
| 5 | `deepseek-v4-flash` | 304B | 1.05M | `minimax-m2` |
| 6 | `glm-5` | 753B | 1.05M | `kimi` |
| 7 | `kimi` | 1T | 131K | `glm-5` |

`gemma` shares rung 1 as its fallback rather than becoming a near-duplicate
rung. `gemma-small-e4b` remains outside production routing because NRP's
active-model catalog no longer lists it, even though the characterization
probe reached its compatibility endpoint.

Embeddings stay local (`all-MiniLM-L6-v2`, 384-dim) to match `schema.sql`.

The gateway exposes an OpenAI-compatible `POST /v1/chat/completions`:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "what is 2+2?"}]}'
```

The response includes the usual OpenAI `choices`/`usage` shape plus a
`gatoway` metadata block reporting which rung/model was actually used,
routing confidence, cost, and whether the classifier fallback path fired.

## Benchmarks

The default eval runs **16 held-out tasks in two independent eight-turn sessions**:
the original general-purpose suite and a coding/design suite. The training
corpus contains **36 prompts**, including two train neighbors for every new
coding/design neighborhood.

`--suite expanded` adds **16 objectively graded tasks**, for **32 tasks in four
independent eight-turn sessions**. These cover structured extraction, missing
information, instruction following, prompt injection in source text, aggregation,
arithmetic, constraints, optimization, and grounded reasoning. Whole-response
JSON grading requires the correct values, keys, types, and array order. The
new tasks remain held out; ten have no qualifying evidence in the historical
bank, so this also measures generalization. See [coverage and limitations](docs/evaluation_breadth.md).

New code tasks cover Python hash maps, intervals and graph traversal, plus
TypeScript sliding windows, stacks and data structures. They include
all-pairs two-sum, Unicode code-point handling and LRU expiry semantics.
Python and TypeScript model output runs only in network-disabled,
resource-limited Docker containers. Hidden tests award fractional credit.
The stability gate compares full pass versus fail for code tasks, while the
bank keeps the fraction.

Live open-ended answers use per-task boolean rubrics. The judge is
openai/kimi, except answers actually produced by that model are judged by
openai/glm-5. Judge failures abort scoring instead of becoming zero scores.
Judge calls are evaluation overhead, excluded from the answer cost comparison.
The new `rubric-json-v2` judge requests schema-constrained output, lowers GLM-5
reasoning effort, rejects truncated output, and never treats reasoning text as
a final grade. Live calibration produced **54/54 valid first-attempt judgments**
with no retries or infrastructure failures. One under-specified reference failed
the quality check; its corrected calibration anchor passed **6/6** repeated
judgments. Ambiguous-answer agreement remains a limitation. See
[calibration results](docs/judge_calibration.md) and
[judge reliability](docs/judge_reliability.md). Historical
scores/checkpoints must not be relabeled as v2 results.

~~~bash
docker pull python:3.13-slim
docker pull node:22-slim

# Offline smoke test: canned answers, scripted code scores, heuristic judge
.venv/bin/python -m gatoway.eval --dry-run --runs 3

# Expanded smoke test; preserves the historical live report
.venv/bin/python -m gatoway.eval --dry-run --suite expanded --runs 3 \
  --report artifacts/expanded_smoke.md --checkpoint artifacts/expanded_smoke.json

# Local Docker integration tests
GATOWAY_DOCKER_TESTS=1 .venv/bin/pytest -q tests/test_code_grader.py

# Live calibration: sends fixtures and rubrics to NRP; choose a fresh output path
.venv/bin/python -m gatoway.judge_calibration --runs 1 \
  --output artifacts/judge_v2/calibration_next.json

# Live eval: configured NRP key and Docker required
.venv/bin/python -m gatoway.eval --runs 3
~~~

The grader probes TypeScript enum transformation in node:22-slim and can
use a locally installed node:24-slim if that probe fails. No npm install or
TypeScript compiler is needed. Ordinary tests use only trusted reference
solutions locally and skip TypeScript reference checks when Node is absent.

**Latest policy screening:** [results](docs/policy_results.md) and
[protocol](docs/policy_comparison.md). Five candidate policies plus the current
router and Kimi control were evaluated on 48 tasks × three repetitions.
Strict evidence and combined paired/price routing made identical decisions:
**26.5% estimated savings, 98.26% mean quality versus Kimi’s 97.68%**.
Both used Kimi for all 16 fresh holdout tasks, preserving quality but saving
nothing on that subset. Price ordering alone saved 72.3% but lost 9.60 quality
points overall. These are screening results, not a demonstrated production
quality guarantee; the price scenario includes the unverified Gemma rate.
Production routing is unchanged.

**Previous expanded evaluation:** [docs/eval_report_expanded.md](docs/eval_report_expanded.md)
records all three live repetitions of the 32-task suite: **89.3% routed versus
92.7% baseline mean quality** (a 3.33-point loss). The
[OpenRouter price comparison](docs/openrouter_cost_comparison.md) estimates **25.5%
lower cost on 54/96 matched pairs**. Full-suite monetary savings are unavailable
because 42 routed Gemma 4 12B answers have no matching catalog price.
The stability gate failed on code_fix, two_sum_pairs, and injected_document.
Objective full passes were 77/84 versus 81/84. Provider-call time fell 63.3%;
reported answer tokens fell 3.9%. These are not accuracy-preserving savings.
The historical 16-task partial result remains in [docs/eval_report.md](docs/eval_report.md).
The task mix and judge changed, so these headline numbers are not directly
comparable with the historical gates.

All 24 live rubric judgments eventually completed, but five truncated attempts
occurred and one checkpointed resume was needed. The calibration's 54/54
first-attempt success did not generalize to every generated answer.

The previous live gate is preserved in
[docs/archive/eval_report_pre_coding.md](docs/archive/eval_report_pre_coding.md). It carries
the historical seed-leakage caveat: editing the source prompts did not remove
existing database rows. The new measured bank contains 288 observations and
no historical seed rows; see [the bootstrap report](docs/bootstrap_report.md)
and [the densification plan](docs/plans/2026-09-24-bank-densification.md).
Historical cost_cents fields remain parameter-count proxies; use the explicit
OpenRouter USD comparison above for monetary estimates, not billed NRP spend.

### Measured bank bootstrap

The bootstrap harness runs each train prompt on every primary model, then
stores the scored outcome in an isolated evaluation database. Completed
observations are checkpointed under artifacts/ and reused on reruns; stable
row IDs prevent duplicate neighbors. Failed answers remain evidence, while
provider or grading infrastructure failures never become fabricated scores.
Difficulty is measured only once all eight models have answered.

~~~bash
# No network, embedding, database, or Docker work:
.venv/bin/python -m gatoway.bootstrap_bank --dry-run

# Live: sends train prompts and answers to configured NRP models/judges.
# Requires Docker and local Postgres, or an explicit source DATABASE_URL.
.venv/bin/python -m gatoway.bootstrap_bank --database gatoway_eval_measured_20260930

# Check real neighbor density before the gate:
.venv/bin/python -m gatoway.bank_density --database gatoway_eval_measured_20260930

# Strict DB-backed gate; aborts on routing/database errors:
.venv/bin/python -m gatoway.eval --database gatoway_eval_measured_20260930 \
  --require-db --runs 3 --checkpoint artifacts/measured_eval_runs.json
~~~

If DATABASE_URL is unset, these isolated-database commands use the local
Docker Compose connection defaults. The target name must start with
gatoway_eval_; existing databases need the bootstrap ownership marker.
The original database is preserved. The live bootstrap is complete: all 36
train prompts have scored observations on all eight models. All 16 eval tasks
have evidence on every rung under the production neighbor query; see
[bank density](docs/bank_density.md). The fresh expanded three-run comparison
completed with rubric-json-v2 against this frozen historical bank; all database
row values were unchanged. See [the live report](docs/eval_report_expanded.md).
Generation uses a 120-second timeout. Judges start with 1024 tokens/120 seconds
and permit a 4096-token/240-second retry for truncated output.

### Agentic coding benchmark

`python -m gatoway.agentic_eval` runs a separate production-oriented coding
suite. Each task starts from a fresh miniature repository, asks the routed
model for a unified diff, applies only validated source-file changes, executes
held-out tests in a network-disabled/resource-limited Docker container, and
feeds failures back for up to three routed turns. The report captures solve
rate, first-pass rate, turns, tier paths/switches, and compute/cost proxy.

```bash
docker pull python:3.13-slim

# Deterministic two-turn smoke test (no model calls)
python -m gatoway.agentic_eval --dry-run

# Live routed NRP run; repeat for a stability result
python -m gatoway.agentic_eval --runs 3

# Run one task while iterating on the harness
python -m gatoway.agentic_eval --task webhook_idempotency
```

The initial suite covers cache boundary semantics, stable dependency planning,
and concurrent webhook idempotency. The committed
`docs/agentic_eval_report.md` records the latest run and labels whether it was
live or scripted. In the current three-run live comparison, the router and
always-frontier control both solved 9/9 task-runs and passed the readiness gate.
Before the ladder expansion, the router used `medium` on all nine successful
first attempts, reducing the
compute/cost proxy by 87.2% and provider latency by 52.4% versus the frontier
control. Methodology, threat boundary, and the path to SWE-bench/Terminal-Bench
integration are documented in `docs/agentic_benchmarks.md`.

## Latency

`python -m gatoway.bench_latency` measures SPEC.md §9's actual deliverable —
"≤100ms added by the gateway on top of native provider latency" — by running
real requests through the full pipeline (real embedding model, live
Postgres session tracking + router query + decision_history write) with only
the provider network call itself stubbed out (explicitly excluded from this
budget by SPEC.md §9, and stubbing it keeps the benchmark free to run).
Current result: **p50 26ms, p95 34ms — comfortably under the 100ms target.**

## Layout

- `docker-compose.yml` — Postgres w/ pgvector extension.
- `schema.sql` — `spend_ledger`, `sessions`, `decision_history` tables.
- `gatoway/db.py` — asyncpg connection pool + `migrate()`.
- `gatoway/embeddings.py` — local sentence-transformers embedding (384-dim,
  no API key needed).
- `gatoway/router.py` — top-k per-model outcome selection + context guard +
  confidence-floor fallback + session effectiveness-bar shifting.
- `gatoway/session.py` — session boundary detection, threshold shifting.
- `gatoway/providers.py` — ordered model ladder and litellm-backed adapter.
- `gatoway/circuit_breaker.py` — provider retry/fallback + cooldown state
  machine.
- `gatoway/app.py` — FastAPI gateway wiring the above together.
- `gatoway/seed.py` — cold-start embedding bank seed data.
- `gatoway/bank_corpus.py` — 36 train prompts across sixteen neighborhoods,
  reference answers, execution fixtures, and the source-level eval overlap
  guard. The isolated measured bank contains all 288 model/prompt observations.
- `gatoway/label_seed.py` — interactive CLI to grow the bank with your own
  difficulty labels (no LLM calls needed).
- `gatoway/batch_job.py` — end-of-session quality scoring + bank write-back
  (train-split only).
- `gatoway/eval.py` — benchmark harness, produces `docs/eval_report.md`.
- `gatoway/agentic_eval.py` — isolated multi-turn patch/test/repair harness,
  produces `docs/agentic_eval_report.md`.
- `benchmarks/agentic/` — starter repositories, held-out tests, task metadata,
  and deterministic oracle patches.
- `gatoway/bench_latency.py` — gateway-overhead latency benchmark (SPEC.md §9).
- `tests/` — unit and integration coverage for routing, sessions, provider
  fallback, feedback jobs, both eval harnesses, and the gateway API.
