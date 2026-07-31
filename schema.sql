-- Cost-aware LLM gateway schema (SPEC.md §4)
--
-- Deviation from spec: VECTOR(1536) -> VECTOR(384). This project embeds with
-- a local sentence-transformers model (all-MiniLM-L6-v2, 384 dims) instead
-- of OpenAI embeddings, so the demo runs fully offline without API keys.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS spend_ledger (
    team_id UUID PRIMARY KEY,
    budget_cents INTEGER NOT NULL,
    usage_cents INTEGER NOT NULL DEFAULT 0,
    avg_session_difficulty FLOAT DEFAULT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    team_id UUID REFERENCES spend_ledger(team_id),
    task_keywords TEXT[],
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    turn_count INTEGER DEFAULT 0,
    expected_turn_count INTEGER,       -- from benchmark difficulty label, if known
    quality_score FLOAT,               -- computed at session close
    current_threshold FLOAT DEFAULT 0.5 -- shifted live during the session
);

CREATE TABLE IF NOT EXISTS decision_history (
    routing_id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(session_id),
    model_id TEXT NOT NULL,
    calculated_difficulty FLOAT,
    calculated_effectiveness FLOAT,     -- filled in after outcome is known
    confidence FLOAT,                   -- similarity score of nearest match; low = fallback used
    input_embedding VECTOR(384),
    response_embedding VECTOR(384),
    followup_embedding VECTOR(384) DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- No ANN index (ivfflat/hnsw) yet: ivfflat's default `lists` count is way
-- oversized for a bank this small (tested at 24 seed rows), so each cluster
-- holds ~0-1 vectors and the default probes=1 misses the true nearest
-- neighbor -- confirmed via EXPLAIN ANALYZE returning 1 row for a LIMIT-3
-- query instead of the 3 closest matches. A plain seq scan over
-- decision_history is exact and still fast at this scale (hundreds to low
-- thousands of rows). Add `CREATE INDEX ... USING ivfflat (input_embedding
-- vector_cosine_ops) WITH (lists = sqrt(row_count))` (and tune
-- `ivfflat.probes` at query time) once the bank is large enough that a seq
-- scan is a measured bottleneck -- don't reintroduce it speculatively.
