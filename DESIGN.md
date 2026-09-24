# gatoway: Design Decisions

This document records every design decision in gatoway, from the first MVP
commit to the current state. For each one it gives the reasoning, the
alternatives that were rejected and what they would have cost, and whether
the decision still holds.

It is organized chronologically, because most decisions only make sense
against what came before them. For example, the NRP migration explains why
the ladder has eight rungs, and the failed wide-ladder gate explains why the
router fetches neighbors per model.

**How this document relates to the others**

| Document | Role |
|---|---|
| `DESIGN.md` (this file) | Retrospective index: what was decided, when, why, and whether it still holds |
| `docs/spec.md` | Current architecture spec (v0.3), the "what" |
| `docs/specs/2026-09-04-wide-ladder-design.md` | Deep design for the ladder pivot, the "why" for phases 3–6 |
| `docs/tasks.md` | Original MVP scope and cut list |
| `docs/agentic_benchmarks.md` | Agentic harness methodology and threat boundary |
| `docs/eval_report.md`, `docs/agentic_eval_report.md`, `docs/nrp_characterization.md` | **Generated.** Every run overwrites them. They hold the numbers. |

Measured results change with every run, so this document does not restate
current figures. When a decision depends on a measurement, it names the
report that holds the measurement. Historical figures appear only when they
are fixed facts about a dated gate that drove a decision.

Each entry uses this format:

- **Decision**: what was chosen
- **Why**: the constraint that forced it
- **Rejected**: the alternative and its cost
- **Status**: *Holds*, *Superseded (→ where)*, *Open risk*, or *Deferred*

---

## Table of contents

- [Phase 0: Framing (the spec)](#phase-0-framing-the-spec)
- [Phase 1: MVP (2026-07-31)](#phase-1-mvp-2026-07-31)
  - [1A. Stack and infrastructure](#1a-stack-and-infrastructure)
  - [1B. Data model](#1b-data-model)
  - [1C. Embeddings and the bank](#1c-embeddings-and-the-bank)
  - [1D. Router (three-tier version)](#1d-router-three-tier-version)
  - [1E. Session tracking and threshold shifting](#1e-session-tracking-and-threshold-shifting)
  - [1F. Fallback and circuit breaker](#1f-fallback-and-circuit-breaker)
  - [1G. Gateway API](#1g-gateway-api)
  - [1H. Feedback loop](#1h-feedback-loop)
  - [1I. Evaluation (first version)](#1i-evaluation-first-version)
  - [1J. Latency benchmark and bank tooling](#1j-latency-benchmark-and-bank-tooling)
- [Phase 2: Provider migration to NRP (2026-09-05)](#phase-2-provider-migration-to-nrp-2026-09-05)
- [Phase 3: Wide-ladder design and ordering (2026-09-04)](#phase-3-wide-ladder-design-and-ordering-2026-09-04)
- [Phase 4: Docs consolidation and spec v0.2 (2026-09-05)](#phase-4-docs-consolidation-and-spec-v02-2026-09-05)
- [Phase 5: NRP characterization spike (2026-09-05)](#phase-5-nrp-characterization-spike-2026-09-05)
- [Phase 6: Eval rework (2026-09-06)](#phase-6-eval-rework-2026-09-06)
- [Phase 7: Agentic coding harness (2026-09-06 → 09-07)](#phase-7-agentic-coding-harness-2026-09-06--09-07)
- [Phase 8: Wide ladder and evidence router (2026-09-07)](#phase-8-wide-ladder-and-evidence-router-2026-09-07)
- [Phase 9: Evidence-balanced routing fix (2026-09-08)](#phase-9-evidence-balanced-routing-fix-2026-09-08)
- [Deliberately deferred or rejected](#deliberately-deferred-or-rejected)
- [Current state and known debts](#current-state-and-known-debts)

---

## Phase 0: Framing (the spec)

### 0.1 Route by learned similarity, not static rules

- **Decision**: Pick a model per request by embedding it and matching it
  against a bank of past requests with known outcomes. Do not classify with
  hand-written per-request rules such as keyword lists or prompt length.
- **Why**: Static rules encode one person's guess about what is hard, and
  they never improve. A similarity bank improves as outcomes accumulate.
  Every scored request makes the next routing decision better informed.
- **Rejected**:
  - *Rule-based classifier*: cheap and predictable, but it cannot learn.
    Its quality is capped at the author's intuition.
  - *LLM-as-router* (ask a small model to rate difficulty): adds a model
    call on the hot path, which conflicts with the ≤100 ms overhead budget
    (§0.4). It also makes routing non-deterministic.
- **Status**: *Holds.* The router was coarse until Phase 8, when it still
  bucketed on difficulty cutoffs. The wide-ladder design says so directly
  (design §5.1).

### 0.2 North-star metric: effectiveness / cost, reported against an always-highest baseline

- **Decision**: The headline result is cost reduction versus always using
  the top model, paired with the change in effectiveness. It is measured
  over whole simulated sessions, not single requests.
- **Why**: A cost number alone is meaningless, because "always use the
  cheapest model" wins it trivially. The pair shows the tradeoff directly,
  e.g. "X% cheaper for Y points of quality." Sessions matter because
  threshold shifting (§1E) only operates across turns.
- **Rejected**: Accuracy-only or cost-only reporting. Each hides the other
  half of the tradeoff.
- **Status**: *Holds.* Session-level measurement arrived in Phase 6. Before
  that, the eval measured single requests (§1I), which a later phase
  called out as a gap.

### 0.3 Reuse LiteLLM instead of building provider adapters

- **Decision**: Provider calls go through `litellm.acompletion`. gatoway
  adds only the rung table, a response dataclass, and a single call
  function (`gatoway/providers.py`).
- **Why**: Normalizing providers and streaming is solved, tedious work,
  and it is not the thesis. Spec §1 lists "streaming response
  normalization" as a non-goal and says to reuse LiteLLM.
- **Rejected**: Hand-rolled provider clients. Months of edge cases (retry
  semantics, response shapes, token accounting) for no differentiation.
- **Status**: *Holds.* This choice paid off in Phase 2. Moving from
  Anthropic to NRP was a change of model strings plus `api_base`, not a
  rewrite.

### 0.4 A hard ≤100 ms gateway-overhead budget that excludes provider latency

- **Decision**: The gateway may add at most 100 ms (embedding, router
  query, session bookkeeping, and the ledger write). Provider latency is
  excluded from the budget.
- **Why**: A cost-saving router that noticeably slows every request would
  not be adopted. Provider latency is excluded because the gateway cannot
  control it, and including it would make the budget meaningless.
- **Rejected**: No budget, which invites an LLM-based router and blocking
  enrichment steps on the hot path.
- **Status**: *Holds.* This constraint rules out an LLM classifier, a
  hosted embedding API, and multiple tokenizers on the hot path. Each of
  those rejections below traces back to it.

### 0.5 Strict train/eval split: eval runs never write to the bank

- **Decision**: Only train-split sessions write outcomes back into
  `decision_history`. Benchmark and eval runs never do.
- **Why**: The router *is* its bank. If eval tasks leak in, the eval later
  matches its own answers and every number becomes silently inflated.
- **Rejected**: A shared bank with post-hoc filtering. It is easy to get
  wrong and impossible to audit afterward.
- **Status**: *Holds for the write-back path, and it was not enough.* The
  `is_train_split` gate in `gatoway/batch_job.py` is enforced and tested, but
  it only guards rows the batch job writes. A 2026-09-24 audit found five of
  the eight eval prompts sitting in the hand-authored seed bank, three
  verbatim (§10.1). The rule was written as "eval runs never write back" when
  the invariant it needed to express is "the eval prompts are never in the
  bank, by any path." The design adds an explicit `split` column for
  decomposition (Phase 3, §3.6), which has not been applied yet.

### 0.6 Non-goals: multi-region, SSO/RBAC, streaming normalization

- **Decision**: Explicitly out of scope.
- **Why**: None of them affect whether the routing thesis works, and each
  is large.
- **Status**: *Holds.*

---

## Phase 1: MVP (2026-07-31)

Commit `61bca1d`. Scope was set by `docs/tasks.md`: build the smallest
system that proves the north-star story end to end.

### 1A. Stack and infrastructure

#### 1A.1 Python + FastAPI

- **Decision**: Python 3.11+, FastAPI, uvicorn.
- **Why**: The ML side (sentence-transformers) and LiteLLM are both
  Python-first. FastAPI provides async request handling and pydantic
  validation with almost no boilerplate. `TestClient` also lets the latency
  benchmark drive the real app in-process.
- **Rejected**: A Go or Node gateway, which would be faster at the HTTP
  layer. It would need a second process for embeddings, and the network
  hop would eat into the overhead budget.
- **Status**: *Holds.*

#### 1A.2 Postgres + pgvector as the single datastore

- **Decision**: One Postgres (the `pgvector/pgvector:pg16` image) holds the
  spend ledger, sessions, decision history, and the embedding bank.
- **Why**: The bank must be joined with outcomes and sessions. Keeping
  vectors and relational data in one store means one transaction, one
  backup, and one dependency. At this scale (tens to thousands of rows),
  pgvector's exact search is fast.
- **Rejected**:
  - *A dedicated vector DB* (Pinecone, Qdrant, etc.): a second datastore,
    plus cross-store consistency between vectors and their outcomes, for
    no measured benefit at this size.
  - *An in-memory FAISS index*: lost on restart, and not shared across
    workers.
- **Status**: *Holds.*

#### 1A.3 asyncpg with the pgvector codec registered per connection

- **Decision**: Use a raw `asyncpg` pool (`gatoway/db.py`), with
  `register_vector` called in the pool's `init` hook. There is no ORM.
- **Why**: The queries are few and specific (a windowed cosine kNN, a few
  inserts and updates), so an ORM would add a layer without saving any
  code. Registering the codec lets a plain `list[float]` bind to
  `VECTOR(384)`.
- **Rejected**: SQLAlchemy, which `docs/tasks.md` allowed. It is
  unnecessary for about six queries. The first commit also had a
  text-format vector workaround in `seed.py`. Once the codec was
  registered, that workaround broke inserts, and commit `6152c4d` removed
  it. `seed.to_pgvector` stays as a named no-op passthrough so any future
  encoding change happens in one place.
- **Status**: *Holds.* `batch_job.py` still carries a `::vector` cast and
  a comment saying the pool has no codec. That comment is out of date. The
  cast is harmless but should be removed the next time that file is
  touched.

#### 1A.4 `schema.sql` applied by `python -m gatoway.db migrate`; no migration framework

- **Decision**: One idempotent SQL file using `CREATE ... IF NOT EXISTS`.
- **Why**: There are three tables and nothing has been deployed, so there
  is no data to migrate forward yet.
- **Rejected**: Alembic. That is the right tool once there is a deployed
  database whose schema must evolve without data loss. That point arrives
  with the design's `parent_routing_id`/`split` columns (design §7.4).
- **Status**: *Holds for now.* It needs revisiting when the first `ALTER`
  lands.

#### 1A.5 Everything that needs a paid key is optional

- **Decision**: Local embeddings, a `--dry-run` eval mode that is
  auto-selected when no API key is set, and a latency benchmark with a
  stubbed provider.
- **Why**: A portfolio project that cannot run without a credit card does
  not get run. Every piece of the gateway except live model output can be
  exercised offline.
- **Status**: *Holds.* After Phase 2 the provider is free for researchers
  (NRP), but offline paths still matter for CI and for reviewers without
  an NRP key.

#### 1A.6 pytest with `asyncio_mode = "auto"` and `testpaths = ["tests"]`

- **Decision**: Auto async mode. Test discovery is restricted to `tests/`.
- **Why**: Without `asyncio_mode` set, every `@pytest.mark.asyncio` test
  failed unless each invocation passed the flag by hand. `testpaths`
  exists because `benchmarks/agentic/*/grader_tests/` are held-out
  fixtures. They must run only inside their grading container, and they
  fail against the unsolved starter repos, which is intended.
- **Status**: *Holds.*

### 1B. Data model

#### 1B.1 Three tables: `spend_ledger`, `sessions`, `decision_history`

- **Decision**: This split follows spec §4.
- **Why**: The three tables change at different rates and have different
  owners. The ledger is per team and slow-changing. Sessions are per
  conversation and mutable while live. Decision history is append-only
  and is the bank itself.
- **Status**: *Holds.*

#### 1B.2 `decision_history.model_id` is a concrete model string, not a tier

- **Decision**: Store the actual model that answered (for example
  `openai/qwen3-small`), not the bucket it was routed from.
- **Why**: Model identity is a fact, and a tier is an interpretation that
  may change. This turned out to be the key decision behind Phase 8. When
  the ladder widened, the schema already supported per-model evidence, and
  only the router had to change (design §5.1).
- **Status**: *Holds.*

#### 1B.3 `confidence` column as the fallback signal

- **Decision**: Every decision records the similarity of the match that
  drove it. A low value means the fallback path chose the model.
- **Why**: It makes "we didn't know, so we guessed" visible in the data
  and separable in analysis, so unconfident rows cannot count as evidence.
- **Status**: *Holds.*

#### 1B.4 Three embedding columns: input, response, followup

- **Decision**: Store `input_embedding`, `response_embedding`, and a
  nullable `followup_embedding`.
- **Why**: The router only reads `input_embedding`. The other two are
  cheap to store and support future outcome signals, such as whether the
  follow-up message looks like a correction.
- **Rejected**: Storing only the input. It is cheaper, but response and
  follow-up could never be recovered for past rows.
- **Status**: *Holds, partly speculative.* `followup_embedding` is never
  written today. It is the one column in the schema that exists "for
  later."

#### 1B.5 Nullable `session_id` for seed rows

- **Decision**: Seed rows have `session_id = NULL`.
- **Why**: Seed rows are bank entries, not traffic. A fake session per row
  would create sessions that never happened.
- **Status**: *Holds.*

### 1C. Embeddings and the bank

#### 1C.1 Local `all-MiniLM-L6-v2`, 384 dimensions

- **Decision**: Use sentence-transformers locally, loaded lazily on first
  call. `schema.sql` uses `VECTOR(384)`, which deviates from the spec's
  original `VECTOR(1536)`.
- **Why**: It needs no API key, adds no network hop to the overhead
  budget, and is small enough to load quickly. It is good enough for
  nearest-neighbor matching over short prompts. Lazy loading means tests
  that mock `embed` never load the model.
- **Rejected**:
  - *OpenAI `text-embedding-3` (1536 dims)*: it needs a paid key and adds
    network latency on the hot path.
  - *NRP's `qwen3-embedding`* (considered again in Phase 3): free, but it
    requires a schema migration plus a full re-seed, and nothing showed
    MiniLM was the bottleneck.
- **Status**: *Holds.* In spec v0.2 the spec was changed to match the code
  (Phase 4).

#### 1C.2 No ANN index; exact sequential scan

- **Decision**: Drop the spec's `ivfflat` index and rely on an exact scan.
- **Why**: This was measured, not assumed. ivfflat's default `lists` value
  was far too large for a 24-row bank, so each cluster held about 0–1
  vectors and the default `probes=1` missed the true nearest neighbor.
  `EXPLAIN ANALYZE` returned one row for a `LIMIT 3` query, and several
  eval tasks were misrouted. An exact scan is correct, and at hundreds to
  low thousands of rows it is still fast. The whole gateway overhead
  (§1J.1) stays well inside budget.
- **Rejected**: A tuned ivfflat (`lists ≈ sqrt(rows)`) or HNSW. Both are
  right eventually, but tuning an ANN index for a bank this small means
  tuning for noise. `schema.sql` states the trigger for re-adding one:
  when the sequential scan becomes a measured bottleneck.
- **Status**: *Holds.* The rationale is written in `schema.sql`, and
  spec v0.2 was corrected to match.

#### 1C.3 Cold-start seed bank (`gatoway/seed.py`)

- **Decision**: 24 hand-written prompt/response pairs, each with a
  hand-labeled difficulty and a high synthetic effectiveness (0.85–0.98),
  inserted before any traffic.
- **Why**: Without seeds, every early request falls below the confidence
  floor and gets the fallback model regardless of difficulty, so the
  router would learn nothing from its first requests. Seeds make the day-one
  routing distribution non-degenerate.
- **Rejected**: A heuristic difficulty scorer for cold start. That would
  be the static-rules approach from §0.1 under another name.
- **Status**: *Superseded (→ Phase 10).* Two problems, both structural. The
  bank's small size became the central issue in Phases 3, 8 and 9. And the
  prompts were written by hand alongside the benchmark tasks, so five of them
  restate an eval prompt — the seed set was authored the way a person
  naturally writes examples, by reaching for the same cases. Every seed row's
  effectiveness is also an assumption (0.85–0.98), not an observation, so all
  of them clear the 0.7 bar by construction.

#### 1C.4 Seed script is not idempotent

- **Decision**: Each run appends fresh `uuid4` rows.
- **Why**: It is meant to be run once against a fresh database. Making it
  idempotent would need a natural key that seed rows do not have.
- **Rejected**: Upsert on prompt text, which would need a new unique
  column only for seeds.
- **Status**: *Holds, documented.* This became a real hazard for eval
  isolation. Phases 6–9 ran every live eval against a separate database
  containing exactly the seed rows, so a doubled seed could not skew
  results.

### 1D. Router (three-tier version)

#### 1D.1 Nearest single neighbor → difficulty → bucket into cheap/medium/frontier

- **Decision**: `LIMIT 1` nearest neighbor. Take its
  `calculated_difficulty`, shift it by the session threshold, and bucket
  it with `DIFFICULTY_CHEAP_MAX = 0.33` and `DIFFICULTY_MEDIUM_MAX = 0.66`
  into Haiku, Sonnet, or Opus.
- **Why**: It was the smallest router that could demonstrate the thesis,
  and three tiers matched the three commercial model sizes available at
  the time.
- **Rejected**: k-NN voting. It was not justified with a 24-row bank at
  the time, although this became the fix later.
- **Status**: *Superseded (→ Phase 8).* The design names the flaw: the
  router discarded model identity at bucket time and rebuilt it from two
  hard-coded cutoffs, which contradicts §0.1.

#### 1D.2 Confidence floor 0.3 → fallback tier

- **Decision**: If the best similarity is below 0.3, ignore the match and
  use the fallback tier (originally `medium`, i.e. Sonnet), and mark the
  row low-confidence.
- **Why**: A weak match is worse than no match, because it routes with
  false confidence. A mid-ladder default limits the damage in both
  directions.
- **Status**: *Constant holds* (`router.CONFIDENCE_FLOOR`). The fallback
  target changed to `gpt-oss` in Phase 8.

#### 1D.3 Error contract: `classify()` propagates errors; the gateway owns the fallback

- **Decision**: The router never catches embedding or database errors.
- **Why**: Spec §5 defines a specific classifier-failure path (a single
  request that bypasses the breaker). If the router swallowed errors, it
  would silently return a decision, and that state-machine branch could
  never run.
- **Status**: *Holds* (documented in the `router.py` module docstring).

### 1E. Session tracking and threshold shifting

#### 1E.1 Sessions in Postgres, not Redis

- **Decision**: The spec's diagram puts live session state in Redis. The
  MVP uses Postgres, and `SessionTracker` is stateless over the pool.
- **Why**: One datastore instead of two. Because the tracker holds no
  state, multiple gateway workers stay consistent. The measured overhead
  (§1J.1) shows Postgres round-trips fit comfortably in budget.
- **Rejected**: Redis. `docs/tasks.md` sets the trigger: "swap to Redis
  only if turn latency becomes a real problem." It has not.
- **Status**: *Holds.*

#### 1E.2 Naive keyword extraction for task-boundary detection

- **Decision**: Lowercase the text, drop a hard-coded stopword list and
  tokens shorter than 3 characters, and keep the top 8 words by
  (frequency, length). A turn belongs to the same session if at least 20%
  of the stored keywords reappear.
- **Why**: Boundary detection only needs to be roughly right, and the cost
  of an error is small: a split session resets the threshold to default.
  NLTK or spaCy would be a large dependency for a heuristic.
- **Rejected**: TF-IDF (it needs a corpus), a small local model
  (latency, plus another model to maintain), and embedding drift (a
  plausible upgrade, but it adds an embedding call per turn).
- **Status**: *Holds.* Spec §10 lists this as an open question.

#### 1E.3 Linear threshold shift, capped at 0.9

- **Decision**: `threshold = 0.5 + max(0, turns/expected − 1) × 0.4`,
  capped at 0.9. When the expected turn count is unknown, it defaults
  to 5.
- **Why**: Normalizing by the expected turn count is how the spec tells a
  naturally long task apart from a struggling one. A linear step is the
  simplest monotonic function. The cap prevents a very long session from
  demanding effectiveness no model can show.
- **Rejected**:
  - *Historical cluster-average expected turns*: this is what the spec
    asks for. It needs enough session history per cluster to be
    meaningful, and that history does not exist yet. The fixed default of
    5 is documented as the stand-in.
  - *Nonlinear or step curves*: nothing measured favors one shape over
    another.
- **Status**: *Holds.* In Phase 8, the thing the threshold shifts changed
  (from difficulty to the effectiveness bar), but the formula did not.

### 1F. Fallback and circuit breaker

#### 1F.1 Two independent failure paths

- **Decision**: If the classifier fails, send a single request to the
  fallback model and bypass the breaker. If the provider fails, retry once
  on a different model in the same tier, and after 3 consecutive failures
  put the tier into a 60 s cooldown.
- **Why**: These are different faults. A classifier failure is gatoway's
  own problem and says nothing about provider health, so it should not
  trip a breaker. A provider failure is external, and repeated hammering
  makes it worse.
- **Status**: *Holds* (spec §5, `gatoway/circuit_breaker.py`).

#### 1F.2 Primary + one fallback per tier; failure counted per tier

- **Decision**: `candidates[:2]`. The tier's failure counter increments
  only when both models fail.
- **Why**: One retry covers transient single-backend faults without
  multiplying latency. Counting per tier matches the routing unit: the
  router picks tiers, so tiers are what should cool down.
- **Rejected**: Per-model breakers. They are more precise, but then the
  router would need to route around individual cooling models, which is a
  second routing system.
- **Status**: *Holds.*

#### 1F.3 In-process breaker state with simple half-open behavior

- **Decision**: A dict plus an `asyncio.Lock` in one process. When the
  cooldown expires, the next call is allowed and its outcome decides the
  state. `time_fn` and `cooldown_seconds` are injectable.
- **Why**: The MVP runs one gateway instance. Breaker state is a soft
  optimization, and losing it on restart means some failures are retried
  sooner, nothing worse. The injection points let tests exercise the 60 s
  cooldown without sleeping.
- **Rejected**: Redis-backed shared state. It is needed once there are
  several gateway instances, and not before.
- **Status**: *Holds for single-instance.* It has a known ceiling:
  multi-worker deployments give each worker its own breaker.

### 1G. Gateway API

#### 1G.1 OpenAI-compatible `POST /v1/chat/completions` with a `gatoway` metadata block

- **Decision**: Accept and return the OpenAI chat shape. Any client
  `model` field is accepted and ignored. Routing metadata goes in an
  additional `gatoway` key.
- **Why**: Existing SDKs and agent frameworks work just by changing the
  base URL. The extra key is invisible to clients that don't read it and
  inspectable by those that do.
- **Rejected**: A custom API, which would force every client to integrate
  specially.
- **Status**: *Holds.* Tool-call fields are not passed through yet. That
  is the stated prerequisite for pointing SWE-bench-style agents at the
  gateway (`docs/agentic_benchmarks.md`).

#### 1G.2 Route on the last user message only

- **Decision**: `_last_user_text()` supplies the routing text. The full
  message list is still sent to the provider.
- **Why**: The latest ask is what determines difficulty. Embedding the
  whole transcript would blur the signal toward the conversation's
  opening, and session history is already accounted for by threshold
  shifting.
- **Status**: *Holds.*

#### 1G.3 Unknown `session_id` starts a client-named session; errors are OpenAI-shaped

- **Decision**: If a client sends a `session_id` the gateway has never
  seen, start a session with that ID instead of returning a 500.
  Exhausted providers return 503, and oversized input returns 400
  `context_length_exceeded`. Both use OpenAI's error shape.
- **Why**: Clients often generate their own IDs. OpenAI-shaped errors let
  SDK retry logic behave normally.
- **Status**: *Holds.*

#### 1G.4 No auth, rate limiting, or DI framework; a placeholder team ID

- **Decision**: Requests without a `team_id` fall under an all-zeros UUID.
- **Why**: These are non-goals (§0.6), and the thesis does not depend on
  them.
- **Status**: *Holds.* This is the main reason the gateway is not
  production-deployable as it stands.

#### 1G.5 Structured logs instead of OpenTelemetry

- **Decision**: `logger.info` with key=value fields per request.
- **Why**: The spec's OTel → Prometheus → Grafana stack is three services
  for a single-process demo. Log lines carry the same fields.
- **Status**: *Deferred.* Spec §10 still lists the span schema as open.

### 1H. Feedback loop

#### 1H.1 Session quality = turns relative to expected

- **Decision**: `quality = clamp(1 − (turns − expected)/expected, 0, 1)`.
  Finishing within the expected count scores 1.0, and needing twice as
  many turns scores 0.0.
- **Why**: There is no correctness or sentiment signal in live traffic.
  Turn overrun is the only outcome signal available without asking the
  user, and it matches the threshold-shift logic.
- **Rejected**: An LLM judge over the transcript, which is expensive,
  non-deterministic, and out of MVP scope. Explicit thumbs up/down needs
  client UI.
- **Status**: *Holds, weak.* It is documented as a proxy for "the user
  didn't have to grind," not as a correctness measure.

#### 1H.2 Last decision as the session's representative embedding

- **Decision**: Write back the most recent decision's embeddings and
  model, with the session quality as `calculated_effectiveness`.
- **Why**: It is simple, and the last turn is the one whose model choice
  the session outcome most directly judges.
- **Rejected**: Averaging embeddings across turns, which blurs distinct
  sub-asks into a centroid that matches nothing well.
- **Status**: *Holds, documented simplification.*

#### 1H.3 EMA for `avg_session_difficulty`

- **Decision**: α = 0.3 exponential moving average.
- **Why**: The ledger has no session count, so an exact running mean
  would need a new column. An EMA with α = 0.3 is responsive without
  letting one sample overwrite the average.
- **Status**: *Holds.*

### 1I. Evaluation (first version)

#### 1I.1 Hand-written 8-task suite, pre-registered scoring per task type

- **Decision**: Four exact-match tasks, plus four scored by an "LLM judge"
  that is really a length-and-keyword heuristic. The scoring method is
  fixed per task before any routing (FrontierMath-style taxonomy, spec
  §8).
- **Why**: Deciding the scoring method in advance prevents choosing
  whichever scorer flatters the router. A real LLM judge was out of MVP
  scope.
- **Rejected**: Public benchmarks such as MMLU. Their tasks are
  single-shot multiple choice, which is the wrong shape for a
  session-aware router.
- **Status**: *Partly superseded (→ Phase 6).* The heuristic judge turned
  out to be the biggest source of noise in the project.

#### 1I.2 Eval runs standalone, preferring the real router and degrading to an approximation

- **Decision**: `gatoway.eval` calls `router.classify()` in-process when
  Postgres is reachable. Otherwise it uses `approximate_rung()` on the
  task's own difficulty label.
- **Why**: The eval should not require the HTTP server, and it should
  degrade to something runnable without a database, not crash.
- **Rejected**: Going through HTTP. That tests FastAPI instead of routing
  and needs a running server.
- **Status**: *Holds.* `approximate_rung` is documented as eval-only, and
  production never calls it. Reports state which path was used.

#### 1I.3 Dry-run with canned responses in quality bands

- **Decision**: Hand-written low/mid/high responses per task, so an
  offline run produces a report that is not flat.
- **Why**: A dry run where everything scores the same tests nothing.
- **Status**: *Holds.* It is always labeled in the report as not being
  evidence of model quality.

### 1J. Latency benchmark and bank tooling

Commit `6152c4d`.

#### 1J.1 `bench_latency.py`: real pipeline, stubbed provider

- **Decision**: Drive the real FastAPI app through `TestClient` with the
  real embedding model and the live Postgres session, router, and ledger
  write. Only the provider call is replaced by an instant stub.
- **Why**: This measures exactly spec §9's quantity (overhead, excluding
  provider latency), costs nothing, and needs no key. The result is
  recorded in `README.md`.
- **Rejected**: Timing with live providers, which would measure the
  provider rather than the gateway.
- **Status**: *Holds.* In Phase 5 this benchmark was explicitly ruled out
  as a way to measure model latency, because it measures the opposite
  quantity.

#### 1J.2 `label_seed.py`: interactive human labeling with no LLM calls

- **Decision**: A CLI prompts for a 0–1 difficulty per candidate prompt
  and inserts each answer immediately. The rung is derived from the
  difficulty, and `response_embedding` is left NULL.
- **Why**: The router is only as good as its bank. Human labels are the
  cheapest trustworthy way to grow it. Inserting immediately means Ctrl-C
  loses nothing.
- **Status**: *Holds.* Each label is stored with a fixed effectiveness of
  0.9, following seed.py's convention that a row means "handled well at
  this rung." That makes these rows count as evidence for the router. It
  is a label-derived assumption, not an observed outcome.

---

## Phase 2: Provider migration to NRP (2026-09-05)

Commit `0a983e7`.

#### 2.1 Replace Anthropic/OpenAI tiers with NRP-hosted open-weights models

- **Decision**: All tiers point at NRP's single OpenAI-compatible endpoint
  (`https://ellm.nrp-nautilus.io/v1`), authenticated with `NRP_API_KEY`.
  The three tiers were remapped by size: cheap was `gemma-small`
  (12B), medium was `qwen3-small` (27B), and frontier was `qwen3` (180B).
- **Why**: NRP is free for researchers and educators, so live evals can be
  repeated as often as rigor requires (three-run gates, controls). Running
  a three-run frontier-model control on commercial APIs would cost enough
  to discourage re-running.
- **Rejected**: Staying on commercial APIs. They give real prices and
  better models, but repeat runs cost money.
- **Status**: *Holds.* The cost is that there is no real price signal
  (§2.2).

#### 2.2 Cost proxy = total parameter count, flat across input and output

- **Decision**: `cost_cents = params_B × (in + out) / 1e6`. For example, a
  1T-parameter model costs 1000¢ per million tokens. Only relative
  ordering is meaningful.
- **Why**: NRP bills nothing and publishes no prices. Parameter count is
  published, stable, and roughly tracks serving cost, so it is the only
  defensible ordering signal available. Input and output are priced the
  same because weighting them differently would be inventing numbers.
- **Rejected**:
  - *Active parameters*: this is closer to real inference cost for MoE
    models, but it is unpublished for most of the inventory. Using it
    would mean mixing measured values with guesses.
  - *Measured latency*: tried in Phase 5, and it did not discriminate
    between models.
  - *Commercial price lookalikes*: invented numbers.
- **Status**: *Holds, with an open risk.* MoE models (`qwen3` is 180B
  total, about 6B active) could reorder much of the ladder under an
  active-parameter proxy (design §4.4). Every report states that cost is
  a proxy.

#### 2.3 `reasoning_content` fallback when `content` is empty

- **Decision**: `content = message.content or message.reasoning_content
  or ""`.
- **Why**: Reasoning models can return an empty `content`, and downstream
  embedding and scoring must never receive `None`.
- **Rejected**: Raising an error. That is arguably more correct, and the
  code comment says so.
- **Status**: *Holds, flagged.* A `ponytail:` comment records that this
  path is untested. If it ever fires, it would embed chain-of-thought as
  the answer, and the comment recommends raising instead if that happens.

#### 2.4 Unwired Ollama stub kept out of the routing table

- **Decision**: The original `"ollama"` entry was not referenced by any
  router lookup.
- **Why**: `docs/tasks.md` required a stub, not a live rung, and keeping
  it separate stopped the breaker from calling it by accident.
- **Status**: *Superseded.* It was dropped when `TIER_MODELS` became
  derived from `MODEL_LADDER` (Phase 8). It was dead code.

---

## Phase 3: Wide-ladder design and ordering (2026-09-04)

Commit `58b615d` (`docs/specs/2026-09-04-wide-ladder-design.md`). NRP
offers roughly ten distinct models from 12B to 1T parameters. Three tiers
wasted most of that range, so this phase designed a wider ladder.

#### 3.1 Work order: scorer → bank density → ladder width → decomposition

- **Decision**: Do not widen the ladder until the eval can tell adjacent
  rungs apart.
- **Why**: Two measurements from the migration. (1) Over four back-to-back
  runs, the four judge-scored tasks swung between 0.31 and 1.00 with the
  same model and prompt, while exact-match tasks scored 1.00 every time.
  (2) The router bucketed on one neighbor from 24 rows. A scorer that
  cannot distinguish 0.31 from 0.60 cannot distinguish a 27B rung from a
  31B rung. Widening first would have produced numbers that look more
  precise and mean less.
- **Rejected**: The original plan, which was to widen the ladder first
  because that is the visible feature.
- **Status**: *Holds.* It was followed. Phase 6 (scorer) gated Phase 8
  (ladder).

#### 3.2 Portfolio credibility as the target; negative results can ship

- **Decision**: The deliverable is "a wide ladder plus an eval whose
  numbers hold up to questioning." Decomposition may ship as a documented
  negative result.
- **Why**: For a portfolio artifact, one honest failed gate is worth more
  than a feature that quietly does not pay for itself.
- **Status**: *Holds.* The project has recorded several negative results:
  the latency probe, the first wide-ladder gate, and the stale agentic
  report.

#### 3.3 Define all rungs; let the eval prune them

- **Decision**: Configure every distinct size band and remove rungs only
  when evidence shows they are never selected.
- **Why**: Choosing the "real" rungs in advance is a guess. A rung the
  bank never selects is evidence, and removing it afterward is a
  defensible finding.
- **Status**: *Holds.* Pruning has not happened, because the bank is not
  yet dense enough for "never selected" to mean anything (Phase 9).

#### 3.4 Context window is a hard filter, not a tie-breaker

- **Decision**: Filter rungs by context capacity before considering cost.
  This applies everywhere, including the fallback.
- **Why**: A 200K-token request cannot go to a 131K model at any price.
  Treating context as a soft preference would route requests that
  guarantee a provider error.
- **Status**: *Holds.* It is implemented in the router, the fallback,
  and the breaker (Phase 8).

#### 3.5 Escalation routing considered and deferred

- **Decision**: Do not build "try the cheapest model, verify, escalate."
- **Why**: It needs a verifier, which is the scorer problem again, and it
  multiplies latency per request.
- **Status**: *Deferred.* It is worth revisiting only if the
  low-confidence fallback is shown to cost real money. The agentic harness
  uses a limited form (§7.4), where test execution acts as the verifier.

#### 3.6 Decomposition treated as bank densification behind a cost gate

- **Decision**: A splitter's subtasks each go through the unchanged
  `classify()`. Subtask rows carry `parent_routing_id` and inherit the
  parent's `split`. The feature ships only if (splitter + N subtask
  calls) beats one frontier call on cost per passing outcome.
- **Why**: Atomic subtasks cluster tightly and match well, and one task
  writes N rows. That attacks bank sparsity directly. Split inheritance
  exists because decomposing a held-out eval task would otherwise leak N
  rows into the bank.
- **Status**: *Not started* (build step 5). The schema columns are
  designed but not applied.

---

## Phase 4: Docs consolidation and spec v0.2 (2026-09-05)

Commits `2fd9211`, `de8f820`, `96fd15b`, `13d6564`.

#### 4.1 Move docs under `docs/`; README stays at the root

- **Decision**: `SPEC.md` → `docs/spec.md`, `TASKS.md` → `docs/tasks.md`,
  and `eval_report.md` → `docs/eval_report.md`. Designs go in
  `docs/specs/` and plans in `docs/plans/`.
- **Why**: The root was accumulating documents. README stays at the root
  by convention.
- **Status**: *Holds.* `DESIGN.md` also sits at the root, as the
  top-level design index.

#### 4.2 Leave `SPEC.md §N` references in docstrings unchanged

- **Decision**: About sixty docstring references were left as they were.
  Only real path references changed (README links and
  `eval.REPORT_PATH`), and a test (`tests/test_eval_paths.py`) protects
  the report path.
- **Why**: Those references name a section, not a file path, and remain
  accurate. Rewriting them would be churn with some risk of breakage.
- **Status**: *Holds.*

#### 4.3 When spec and code disagree, the spec follows the code

- **Decision**: Spec v0.2 adopted the implementation's `VECTOR(384)`,
  removed the ivfflat index, replaced "default to Sonnet" with a named
  fallback rung, and closed two open questions.
- **Why**: In every disagreement the code was right and had a written
  rationale (see §1C.2). A spec that contradicts working code leads
  readers to "fix" the correct version.
- **Status**: *Holds.* Spec v0.3 (2026-09-07) continued this for the
  ladder.

#### 4.4 Implementation plans are written per build step, against the previous gate's actual numbers

- **Decision**: Steps 1 and 2 shared one plan. Steps 3, 4, and 5 each get
  their own plan, written after the preceding gate produced results.
- **Why**: Writing step 4's plan before step 3's numbers exist means
  planning against assumptions, which is what the design exists to avoid.
- **Status**: *Holds.*

---

## Phase 5: NRP characterization spike (2026-09-05)

Commits `ff68dee`, `842be5b`, `7030a8d`, `54c3581`.

#### 5.1 A dedicated probe (`gatoway/characterize.py`), not `bench_latency.py`

- **Decision**: A new script lists `/v1/models`, sends each chat model a
  trivial prompt with `max_tokens=5` over N rounds, and records the served
  model ID, availability, and median latency.
- **Why**: `bench_latency.py` stubs out the provider on purpose, so it
  measures gateway overhead, the opposite of what the ladder needs. The
  original design mistakenly said to reuse it, and the implementation plan
  corrected that.
- **Status**: *Holds.*

#### 5.2 Deduplicate models by served model ID

- **Decision**: Collapse NRP names that resolve to the same served model
  (for example, `gemma-small`, `gemma4-small`, and `gemma4-12b` are one
  12B model).
- **Why**: Building the ladder from the raw `/v1/models` list would have
  created phantom rungs, i.e. three "different" models with identical
  quality and cost.
- **Status**: *Holds.* The distinct-model count is in
  `docs/nrp_characterization.md` and design §4.1.

#### 5.3 Latency as a second cost signal: recorded as a negative result

- **Decision**: The latency check did not discriminate between models, so
  design §4.4's mitigation is marked *unproven*, not validated.
- **Why**: A 250× parameter range compressed into roughly a 2× latency
  band, `gemma` (31B) measured slower than `kimi` (1T), and one model
  reached through three aliases showed very different medians within
  minutes. With 5 output tokens, fixed overhead dominates, so more rounds
  cannot help. A tokens/sec probe over a long generation might.
  Recording this as a success would have told the ladder step that its
  cost model had been checked when it had not.
- **Rejected**: Reading the inversion as "the cost model is wrong." It
  was the probe that was wrong. Commit `7030a8d` removed a leftover
  sentence that implied otherwise.
- **Status**: *Open risk.* Parameter counts remain the only evidence for
  the cost order.

#### 5.4 Context windows are not verified by the probe

- **Decision**: Do not check off context windows until they have a
  source. `gemma-small-e4b`'s 262K was downgraded to "unconfirmed."
- **Why**: The probe never measures context, and `/v1/models` returns
  only `id/created/object/owned_by`. Context is a hard routing constraint
  (§3.4), so a guessed value would let the router accept requests a model
  cannot hold.
- **Status**: *Resolved in Phase 8.* The values come from NRP's
  managed-model matrix and are hard-coded in
  `providers.MODEL_CONTEXT_TOKENS`, with a note that lifecycle changes
  must update that table explicitly.

#### 5.5 The characterization report is fully generated and disposable

- **Decision**: `docs/nrp_characterization.md` contains only generated
  output plus a generated provenance footer. The analysis lives only in
  the design doc.
- **Why**: A hand-appended analysis section would be silently deleted by
  the next re-run. Appending instead was considered and rejected, because
  analysis of run 1 placed next to run 3's table is quietly wrong, which
  is worse than being deleted. Every claim in the removed section was
  already in the design doc. The footer is generated for the same reason:
  a hand-written warning would be removed by the very re-run it warns
  about.
- **Status**: *Holds.* This document follows the same rule. It cites the
  generated reports instead of copying their numbers.

#### 5.6 `httpx` moved to runtime dependencies

- **Decision**: `httpx` moved from the dev extra to `[project]
  .dependencies`.
- **Why**: `characterize.py` is runtime code that calls `/v1/models`
  directly, and runtime code must not depend on a dev extra.
- **Status**: *Holds.*

---

## Phase 6: Eval rework (2026-09-06)

Commit `996fb50`. This is build step 3 and the gate for the ladder.

#### 6.1 Execution-based scoring for `code_fix` and `sql_query`

- **Decision**: These two tasks moved from the heuristic judge to
  deterministic execution against pre-registered fixtures.
- **Why**: Spec §8 already said checkable tasks should be scored by
  execution, so this closed a spec gap. It also removed two of the four
  tasks that produced all of the measured variance.
- **Status**: *Holds.*

#### 6.2 Sandboxing model output by restricting what it may contain, not by isolating the process

- **Decision**:
  - *Python*: `ast.parse`, then require exactly one `for` loop and only
    allowlisted node types. Allowed calls are
    `print/range/len/enumerate`, the only free names are `arr` and `n`,
    and integer constants are capped at 10,000. It runs with
    `__builtins__ = {}` and a captured `print`, against three array
    fixtures, including an empty one.
  - *SQL*: an in-memory SQLite database with an authorizer that allows
    only `SELECT`/`READ` and the functions `max`, `dense_rank`, and
    `row_number`, plus a progress handler that caps runtime. There are
    three salary fixtures, including duplicate top salaries.
- **Why**: Model output is untrusted, but these tasks only need a tiny
  language. Allowing only that language is stronger than blocking known
  dangerous constructs, and it needs no Docker for an in-process scorer.
  The fixtures include edge cases (an empty array, duplicate maximums)
  so that a naive answer fails.
- **Rejected**: Running arbitrary Python in a subprocess or container.
  That is the right approach for real code, and the agentic harness does
  it (§7.2). For a one-loop answer it adds a container per score.
- **Status**: *Holds.* Tests include a known-good and a known-bad answer
  per scorer, so a broken scorer cannot silently return 1.00.

#### 6.3 Keep the heuristic judge for open-ended tasks, and report variance

- **Decision**: `multistep_planning` and `hard_math_proof` keep the
  length-and-keyword stub. Every figure is reported as a mean and range
  across runs.
- **Why**: A real LLM judge is a non-goal. It adds cost, and its own
  model choice and variance. Reporting ranges is the honest way to handle
  a scorer that is known to be noisy.
- **Status**: *Holds.* This is the weakest part of the eval, and the code
  comments say so.

#### 6.4 Session-level eval: 8 tasks as consecutive turns, expected 3

- **Decision**: The eight tasks run as one simulated session with an
  expected turn count of 3, so turns 4–8 raise the threshold toward the
  0.9 cap. The report records the threshold and chosen rung for each
  turn.
- **Why**: This was the first eval to exercise threshold shifting at all.
  Spec §8 asks for session-level results. Setting the expected count
  deliberately short guarantees the shift code runs.
- **Status**: *Holds.*

#### 6.5 Stability gate: three runs, and checkable tasks must score identically

- **Decision**: The six exact-match or execution-scored tasks must score
  exactly the same across three consecutive runs, on both the router and
  the baseline side. Generation is pinned (temperature 0, 512 max tokens,
  60 s timeout, one timeout retry).
- **Why**: If deterministic scorers see different results under pinned
  settings, the numbers are noise. The gate turns "is this eval
  trustworthy?" into a pass/fail check that runs before any
  conclusion is drawn.
- **Status**: *Holds.* It passed at the three-tier stage (2026-09-06,
  isolated 24-row bank), which unblocked Phase 8. It has failed since the
  ladder widened. Current status is in `docs/eval_report.md`.

#### 6.6 Live evals run against an isolated bank

- **Decision**: Live gates use a separate database containing exactly the
  seed rows. Older local data was kept elsewhere.
- **Why**: Earlier manual testing and repeated seeding (§1C.4) would
  otherwise change what the router sees between runs, and a gate is only
  meaningful if its input is fixed.
- **Status**: *Holds (procedural).*

---

## Phase 7: Agentic coding harness (2026-09-06 → 09-07)

Commits `b4cf27d`, `f27d47b`. Methodology: `docs/agentic_benchmarks.md`.

#### 7.1 A separate harness and report, not merged into `gatoway.eval`

- **Decision**: `gatoway.agentic_eval` is its own module, writing its own
  report.
- **Why**: Single-response scoring does not show whether a routed model
  can change a repository, survive executable grading, and use failure
  feedback over several turns. Mixing multi-turn repair into the
  lightweight session report would confuse both result sets.
- **Status**: *Holds.*

#### 7.2 Held-out tests executed in a hardened Docker container

- **Decision**: `--network none`, read-only root filesystem and read-only
  bind mount, `--cap-drop ALL`, `no-new-privileges`, 128 PIDs, 256 MB
  memory, 1 CPU, `noexec` tmpfs, uid 65534, `--pull never`, and a 30 s
  timeout. The image tag is resolved to an immutable image ID once in a
  preflight step, used for every task, and recorded in the report.
- **Why**: Generated code is arbitrary code. The host checkout is never
  modified. Pinning the image ID makes runs reproducible even if the tag
  moves.
- **Rejected**: Running tests on the host, which is unsafe, and
  gVisor/Firecracker, which are more isolation than a local benchmark
  needs. The doc states the boundary directly: "a local benchmark
  sandbox, not a hostile multi-tenant execution service."
- **Status**: *Holds.*

#### 7.3 Strict patch protocol: validated unified diffs only

- **Decision**: The model returns one unified diff. The harness rejects
  path traversal, absolute paths, edits to tests, file creation or
  deletion, renames, copies, mode changes, and binary patches. It then
  applies the patch with `git apply --check` before `git apply`.
- **Why**: A model that edits the tests can pass anything, and one that
  writes outside the repo can escape the workspace. An allowlist of
  editable source files is the smallest rule that closes both. Fenced
  diffs with any language label are accepted, because models label them
  inconsistently.
- **Rejected**: Giving the model a shell or editor tool API. That would
  be more realistic, but the harness would then measure tool use rather
  than routing, and the gateway does not yet pass tool calls through
  (§1G.1).
- **Status**: *Holds.* The doc states that this tests iterative repair,
  not a full terminal agent.

#### 7.4 Monotonic rung floor on execution failure

- **Decision**: An invalid diff, a failed test run, or exhaustion of both
  models in a rung advances a minimum rung by one position. The selected
  rung is `max(semantic routing, floor)`, capped at the top.
- **Why**: Without a floor, a low-confidence fallback could send every
  repair attempt back to the same failing model. The floor is expressed
  as a position in the rung order, not hard-coded transitions, so it kept
  working when the ladder widened.
- **Rejected**: Hard-coded tier jumps (for example medium → frontier),
  which broke as soon as the tier set changed.
- **Status**: *Holds.* This is the limited escalation mentioned in §3.5,
  justified here because test execution is a real verifier.

#### 7.5 Expected turns = 1, so a single repair moves the threshold to 0.9

- **Decision**: The agentic session uses `AGENTIC_EXPECTED_TURNS = 1`.
- **Why**: In this protocol, a first-attempt failure is a genuine struggle
  signal. The semantic router should see the maximum bar on repair turns,
  on top of the floor from §7.4.
- **Status**: *Holds.*

#### 7.6 Qwen3 runs in non-thinking mode for patch generation

- **Decision**: Pass `chat_template_kwargs.enable_thinking = False` for
  qwen3 models in this harness only.
- **Why**: A controlled live probe showed that the default mode spent the
  entire 2,400-token allowance on reasoning and stopped at `length` before
  writing a patch. Non-thinking mode returned patches with a normal
  `stop`.
- **Rejected**: Raising `max_tokens`, which costs more and still does not
  guarantee output.
- **Status**: *Holds.* It is scoped to this harness, and the gateway does
  not force it.

#### 7.7 An always-top-rung control run on every task

- **Decision**: Each task runs a second time, from a fresh workspace, with
  every turn pinned to the highest rung.
- **Why**: This separates routing failures (the router picked too low)
  from model or protocol failures (even the top model fails). Without it,
  a failure means nothing.
- **Status**: *Holds.* `--skip-baseline` exists only to make harness
  iteration faster.

#### 7.8 Readiness gate: 3 runs, every task passes at least 2/3, no exhausted rung

- **Decision**: Pass/fail criteria for "production-ready routing" on this
  suite.
- **Why**: Two out of three tolerates one flaky provider call without
  hiding a systematic failure. Treating exhausted rungs as a failure
  catches runs that passed only because a fallback model rescued them.
- **Status**: *Holds.*

#### 7.9 Oracle patches and a scripted dry run

- **Decision**: Each task ships with an `oracle.patch`. `--dry-run`
  deliberately fails turn 1 and applies the oracle on turn 2.
- **Why**: This proves each task and its grader agree (the oracle
  passes), and it exercises the full loop (isolation, patching,
  observation chaining, threshold movement) deterministically with no
  model calls.
- **Status**: *Holds.*

#### 7.10 Raw trajectories written to the ignored `artifacts/` directory

- **Decision**: Full per-turn JSON (prompts, responses, finish reasons,
  provider failures, grader output) goes to `artifacts/agentic_eval/`,
  which is gitignored.
- **Why**: Trajectories are large and may contain repository content.
  The committed report is the summary, and the trajectories are for
  debugging.
- **Status**: *Holds.*

#### 7.11 Three small synthetic tasks as the starting suite

- **Decision**: `ttl_cache`, `dependency_planner`, and
  `webhook_idempotency`, chosen for boundary semantics, cross-record
  validation, and concurrency correctness respectively.
- **Why**: The tasks are small enough to run cheaply and repeatedly, and
  each targets a known failure mode for models. The doc is clear that
  they do not represent real repositories. The planned scale-up is an
  adapter to SWE-bench/Harbor.
- **Status**: *Holds as a starting gate.* The committed report is from
  the three-tier router and labels itself as historical. The eight-rung
  ladder has not been re-measured on this suite.

---

## Phase 8: Wide ladder and evidence router (2026-09-07)

Commit `5750edd`. This is build step 4. Spec v0.3.

#### 8.1 Eight rungs ordered by total parameter count

- **Decision**: `gemma-small` (12B) → `qwen3-small` (27B) → `gpt-oss`
  (120B) → `qwen3` (180B) → `minimax-m2` (230B) → `deepseek-v4-flash`
  (304B) → `glm-5` (753B) → `kimi` (1T). The ladder is defined once as
  `providers.MODEL_LADDER`. `TIER_MODELS` and `RUNG_NAMES` are derived
  from it.
- **Why**: Every distinct, currently listed NRP chat model gets its own
  size band (§3.3). Having one definition means the router, breaker,
  eval, and seed cannot disagree about the ladder.
- **Status**: *Holds.*

#### 8.2 `gemma` (31B) shares rung 1 as its fallback instead of being its own rung

- **Decision**: 27B and 31B are one rung.
- **Why**: A 15% parameter difference is not a distinguishable cost band,
  and the scorer could not separate the two. As a fallback, `gemma`
  still provides provider redundancy for rung 1.
- **Status**: *Holds.*

#### 8.3 `gemma-small-e4b` characterized but not routable

- **Decision**: It is excluded from the ladder despite passing 3/3 probe
  rounds.
- **Why**: By implementation time, NRP's managed-model catalog no longer
  listed it. It is reachable only through a compatibility alias. A
  production ladder follows the provider's supported lifecycle, not
  whatever endpoint happens to answer.
- **Status**: *Holds.* It remains unnumbered in design §4.2.

#### 8.4 Cross-fallbacks between neighboring rungs

- **Decision**: Each rung's fallback is an adjacent-size model, for
  example `gpt-oss` ↔ `qwen3` and `glm-5` ↔ `kimi`.
- **Why**: NRP rarely has two same-size models, and a fallback of similar
  size keeps the cost and quality change during an outage small.
- **Status**: *Holds.*

#### 8.5 Router: top-k per-model evidence against an effectiveness bar

- **Decision**: Remove `_bucket_tier` and the difficulty cutoffs. Fetch
  scored neighbors and drop any below `CONFIDENCE_FLOOR` (0.3). Then walk
  the ladder from cheapest to most expensive and pick the first rung that
  (a) has enough context, (b) has at least `MIN_OBSERVATIONS` (2)
  confident scored observations, and (c) has a mean effectiveness of at
  least the bar. The bar is `EFFECTIVENESS_BAR` (0.7) plus
  `(threshold − 0.5) × 0.5`.
- **Why**:
  - Choosing a *model* from *per-model outcomes* makes the router match
    the thesis in §0.1. The schema already supported this (§1B.2).
  - `MIN_OBSERVATIONS` stops a single lucky neighbor from promoting a
    model.
  - Threshold shifting keeps its documented meaning ("a struggling
    session pulls in higher rungs"), but now it raises the bar instead of
    inflating difficulty, and `THRESHOLD_SHIFT_SCALE` keeps its value.
- **Rejected**: Keeping difficulty buckets with eight cutoffs. That gives
  "noise with more decimal places": one neighbor's difficulty label split
  eight ways.
- **Status**: *Holds.* The constants are starting values. They are
  intentionally not tuned until the eval is trustworthy, because tuning
  against an unstable scorer is fitting to noise.

#### 8.6 `estimate_tokens = ceil(len(text) / 4)`, not a real tokenizer

- **Decision**: Estimate token count at four characters per token.
- **Why**: The estimate only has to be accurate within an order of
  magnitude, because context windows on the ladder range from 131K to 1M
  (about 8×). Real tokenization would need four tokenizer families on the
  hot path, which conflicts with the overhead budget (§0.4).
- **Rejected**: Using per-model tokenizers. They are accurate but slow,
  and the extra accuracy would not change any decision.
- **Status**: *Holds.* The breaker adds the requested `max_tokens` to the
  input estimate, so the output allowance counts against the window too.

#### 8.7 `gpt-oss` as the fallback rung; oversized requests use the cheapest rung that fits

- **Decision**: `FALLBACK_RUNG = "gpt-oss"` (rung 2) replaces "medium /
  Sonnet." If `gpt-oss`'s 131K window cannot hold the request, the
  fallback becomes the cheapest rung that can. If no rung can hold it,
  the router raises `RequestTooLargeError`, which returns a 400.
- **Why**: It is mid-ladder, so misrouting costs are bounded in both
  directions. `gpt-oss` is also not MoE, so its position in the cost
  ordering does not depend on the open active-parameter question (§2.2).
  The context rule applies to the fallback as well (§3.4).
- **Status**: *Holds.*

#### 8.8 Context enforced in three places

- **Decision**: Context is checked in the router (rung selection), in the
  classifier-failure fallback in `app.py`, and in the breaker, which
  filters each rung's candidate models by *their own* window.
- **Why**: A rung's fallback model can have a smaller window than its
  primary. For example, `qwen3-small` has 1M and its fallback `gemma` has
  262K. Checking only at the rung level would let the fallback receive a
  request it cannot hold.
- **Status**: *Holds.*

#### 8.9 Seeds spread evenly across rungs

- **Decision**: The 24 seed examples are sorted by difficulty and assigned
  in order, three to each rung.
- **Why**: Every rung needs some evidence, or `MIN_OBSERVATIONS` can never
  be met and the rung becomes unselectable by construction.
- **Status**: *Superseded in part by Phase 9.* Spreading rows globally
  turned out not to give per-neighborhood evidence.

#### 8.10 Backward-compatible `tier` names retained

- **Decision**: `TIERS`, `FALLBACK_TIER`, `TIER_MODELS`,
  `tier_for_difficulty`, and the public `tier` field stay as aliases for
  rung names.
- **Why**: The rename touched the eval, the agentic harness, the app, and
  the tests. Aliases let the change land without rewriting every caller
  in one commit.
- **Status**: *Transitional.* The aliases can be removed once callers use
  rung names.

---

## Phase 9: Evidence-balanced routing fix (2026-09-08)

Commits `31c8541` (first gate), `0201467` (fix), `47ee191` (re-gate).

#### 9.1 First wide-ladder gate recorded as failed

- **Decision**: Publish the failure. Savings stayed flat compared with
  three tiers, effectiveness dropped substantially, and the stability
  gate failed. The analysis went into design §8.1.
- **Why**: §3.2 committed to this in advance. The analysis also found the
  cause. Per-task inspection showed that spreading three rows across each
  rung gives global coverage but not two same-model observations within
  any one semantic neighborhood. Most decisions therefore took the
  fallback, or the "highest single observed rung," which is not evidence
  at all.
- **Status**: *Holds (historical record).*

#### 9.2 Fetch neighbors per model, not globally

- **Decision**: A window function, `row_number() OVER (PARTITION BY
  model_id ORDER BY distance)`, returns up to `NEIGHBORS_PER_MODEL` (5)
  nearest *scored* rows *for each routable model*, instead of the global
  top 5.
- **Why**: A global top-k lets a model with many nearby rows, or unscored
  rows, fill every slot, and then no other rung can reach
  `MIN_OBSERVATIONS`. Fetching per model gives every rung a fair chance
  to present evidence. The confidence floor still discards weak matches
  afterward. Filtering to rows with `calculated_effectiveness IS NOT NULL`
  keeps outcome-less rows out of the selection. The gateway's own
  per-request inserts have no outcome until the batch job scores the
  session.
- **Rejected**:
  - *Increasing global k*: this only moves the crowding problem around.
  - *Densifying the seed bank first*: this is still necessary (design
    §8.1), but it does not fix the structural bias of global top-k.
- **Status**: *Holds.* The query does 8 × 5 = 40 row lookups over an exact
  scan, which is fine at the current bank size. It will need an ANN index
  eventually (§1C.2).

#### 9.3 No promotion without evidence: remove "highest observed rung"

- **Decision**: If no rung meets both `MIN_OBSERVATIONS` and the bar,
  route to the explicit fallback (`gpt-oss`) and mark the decision
  low-confidence. Previously, the router fell back to the highest rung
  that had any confident neighbor.
- **Why**: A single high-rung observation is one data point. Promoting on
  it meant one expensive seed row could send a whole cluster to `kimi`,
  which contradicts the reason `MIN_OBSERVATIONS` exists. The
  low-confidence flag keeps these decisions separable in analysis.
- **Rejected**: Keeping "highest observed" as a quality-safe default. It
  is safe but expensive, and it is not evidence-based. That is the same
  objection that removed static buckets.
- **Status**: *Holds.* In the re-gate, most tasks landed on `gpt-oss`,
  which is the expected result for a bank this sparse. The router is
  honestly reporting that it lacks evidence. Figures and the current
  gate status are in `docs/eval_report.md`. The remedy is denser evidence
  per cluster, not a different fallback rule.

---

## Phase 10: Leakage audit and bank densification (2026-09-24)

Plan: `docs/plans/2026-09-24-bank-densification.md`. Not yet implemented.

### 10.1 Seed-time leakage found and recorded before fixing it

- **Finding**: Comparing `seed.py`'s prompts against `eval.BENCHMARK_TASKS`,
  five of eight eval prompts are in the seed bank — `capital_france`,
  `sql_query` and `hard_math_proof` character-for-character, `code_fix` at a
  0.98 similarity ratio, `multistep_planning` reworded only in its opening
  clause.
- **Why it slipped through**: every leakage control in the project guards the
  *write-back* path (§0.5). Hand-authored seed rows never pass through the
  batch job, so nothing checked them. The invariant was stated as a rule about
  code paths when it is really a rule about prompts.
- **Consequence for recorded results**: for five of eight tasks, the router
  matched a row whose rung was assigned by hand, at similarity ≈ 1.0. The
  wide-ladder gate numbers measure the seeding decision as much as the routing
  logic. Worse for the analysis in design §8.1, the one task that found two
  same-rung observations — `capital_france` — is a verbatim leak, so the single
  positive data point is the least trustworthy one.
- **Decision**: record it in the design doc, the spec and the README before
  fixing it, rather than quietly rewriting the prompts. The density diagnosis
  from Phase 9 still stands; its supporting evidence is weaker than it reads.
- **Status**: *Open.* Closed by the plan's Task 1, which adds a similarity
  guard over every prompt list that feeds the bank.

### 10.2 Densify by measuring, not by labeling

- **Decision**: Build a train-split corpus of roughly 20 prompts with
  checkable answers, run every prompt through all 8 rungs, score each response
  with the existing execution scorers, and write one row per (prompt, rung)
  pair.
- **Why**: Each prompt yields 8 rows at one point in embedding space, which is
  exactly the local density `MIN_OBSERVATIONS = 2` requires (§9.1). The label
  is an observed outcome rather than a guess, so failures get recorded too —
  and a 0.0 row is what finally lets the effectiveness bar reject a rung.
  Difficulty also becomes measurable as `1 − mean(score across rungs)`, the
  first difficulty figure in the project that is not hand-assigned.
- **Rejected**:
  - *Manual difficulty labeling via `label_seed.py`*: produces the wrong kind
    of row — a guessed difficulty and a fixed 0.9 effectiveness. Slow, and not
    evidence.
  - *Cross-product over the eval tasks themselves*: leakage by construction,
    which is the mistake §10.1 just documented.
  - *Waiting for real traffic*: correct long term, and the batch job already
    supports it, but there is no traffic.
- **Decision on the old seed rows**: drop them once measured rows exist. Their
  effectiveness values are assumptions that all clear the bar, so they dilute
  measured evidence with guesses.
- **Status**: *Planned.*

---

## Deliberately deferred or rejected

| Item | Status | Reason | Revisit when |
|---|---|---|---|
| Real LLM judge | Rejected for MVP | It adds its own cost, model choice, and variance. Execution scoring replaced it where tasks allow. | Open-ended tasks become central to the eval |
| Escalation routing (cheap → verify → escalate) | Deferred | Needs a verifier, and multiplies latency | Low-confidence fallback shown to cost real money |
| Task decomposition | Not started | Gated on cost per passing outcome | Build step 5 |
| `parent_routing_id` / `split` columns | Designed, not applied | Only needed with decomposition | With decomposition |
| Redis (sessions, breaker, rate limits) | Deferred | Postgres fits the latency budget, and there is one instance | Multi-instance deploy, or turn latency becomes a problem |
| OpenTelemetry / Prometheus / Grafana | Deferred | Three services for a single process | Real deployment |
| ANN index (ivfflat / HNSW) | Removed | Default tuning missed true neighbors at small N | Sequential scan is a measured bottleneck |
| `qwen3-embedding` | Rejected | Migration and re-seed with no measured benefit | MiniLM shown to limit match quality |
| Ollama local rung | Dropped | Stub only, never wired in | A local tier is needed |
| Tool-call passthrough | Not built | Not needed by the current harnesses | Before pointing SWE-bench/Harbor agents at the gateway |
| Auth / RBAC / per-team budgets enforced | Non-goal | Does not affect the routing thesis | Real users |
| Tokens/sec latency probe | Not built | Needed to test the MoE cost-order risk | Before trusting the parameter-count ordering beyond "proxy" |
| Historical-cluster expected turn counts | Deferred | Needs session history that does not exist yet | Enough train-split sessions per cluster |

---

## Current state and known debts

**Works and is tested:** the gateway API, the evidence-based eight-rung
router, context enforcement, the circuit breaker, session tracking, the
train-only feedback loop, both eval harnesses with their gates, the
characterization probe, and the latency benchmark.

**Open risks:**

1. **Bank density.** The router mostly falls back to `gpt-oss` because
   too few task clusters have two same-model scored observations. This is
   the main blocker for pruning rungs and for a passing ladder gate.
1b. **Seed-time eval leakage** (§10.1). Five of eight eval prompts are in the
   seed bank, three verbatim, so every recorded ladder-gate number carries a
   caveat until the guard in the plan's Task 1 lands.
2. **MoE cost ordering** (§2.2, §5.3). The parameter-count proxy has no
   independent validation.
3. **Heuristic judge** (§6.3) on two of eight tasks.
4. **The agentic report is stale.** It was measured with the three-tier
   router and has not been re-run on the eight-rung ladder.

**Documentation state**: `README.md` was brought in line with the
balanced-routing re-gate on 2026-09-24, and design §8.1 carries the leakage
correction from §10.1. `docs/eval_report.md` remains authoritative for any
number, because every run regenerates it. Design §8.1 still describes the
per-model retrieval fix without quoting the re-gate's result, deliberately —
the report holds it.

**Small code debts:**

- `batch_job.py`'s `::vector` casts and comment predate codec
  registration (§1A.3).
- `followup_embedding` is never written (§1B.4).
- The `tier` aliases are transitional (§8.10).
- The untested `reasoning_content` fallback (§2.3).
- Breaker state is per process (§1F.3).
