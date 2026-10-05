from contextlib import asynccontextmanager
import os
from dataclasses import replace

import pytest

import gatoway.bootstrap_bank as module
from gatoway.bank_corpus import TRAIN_PROMPTS
from gatoway.providers import MODEL_LADDER, ProviderResponse


class Pool:
    def __init__(self):
        self.rows = {}
    @asynccontextmanager
    async def acquire(self):
        yield self
    @asynccontextmanager
    async def transaction(self):
        yield
    async def execute(self, query, *values):
        self.rows[values[0]] = values


@pytest.fixture
def fakes(monkeypatch):
    calls = []
    async def provider(model, messages, **kwargs):
        calls.append(model)
        assert kwargs["temperature"] == 0
        return ProviderResponse("answer", model, 1, 2, .1, None)
    async def score(task, response, model, **kwargs):
        return 0.0 if model == MODEL_LADDER[0].primary else 1.0
    monkeypatch.setattr(module, "call_provider", provider)
    monkeypatch.setattr(module, "score", score)
    monkeypatch.setattr(module, "embed", lambda text: [1., 0.])
    return calls


async def test_cross_product_writes_failures_and_measured_difficulty(fakes):
    pool = Pool()
    result = await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:2])
    assert result["written"] == 16
    assert len(pool.rows) == 16
    assert len(fakes) == 16
    for row in pool.rows.values():
        assert row[2] == .125  # 1 - mean([0, 1, 1, 1, 1, 1, 1, 1])
        assert row[4] == 1.0  # observation confidence
    assert sum(row[3] == 0 for row in pool.rows.values()) == 2


async def test_provider_exception_skips_pair_and_does_not_invent_difficulty(monkeypatch, fakes):
    async def provider(model, *args, **kwargs):
        if model == MODEL_LADDER[0].primary:
            raise TimeoutError("offline")
        return ProviderResponse("answer", model, 1, 2, .1, None)
    monkeypatch.setattr(module, "call_provider", provider)
    pool = Pool()
    result = await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:1])
    assert result["written"] == 7
    assert len(result["provider_failures"]) == 1
    assert all(row[2] is None for row in pool.rows.values())


async def test_dry_run_never_calls_provider_embedding_or_database(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("live dependency called")
    monkeypatch.setattr(module, "call_provider", forbidden)
    monkeypatch.setattr(module, "embed", forbidden)
    result = await module.bootstrap(None, prompts=TRAIN_PROMPTS[:1], dry_run=True)
    assert result["written"] == 0
    assert result["scored"] == 8


async def test_scoring_infrastructure_error_propagates(monkeypatch, fakes):
    async def fail(*args, **kwargs):
        raise RuntimeError("judge unavailable")
    monkeypatch.setattr(module, "score", fail)
    pool = Pool()
    with pytest.raises(RuntimeError, match="judge unavailable"):
        await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:1])
    assert not pool.rows


async def test_resume_reuses_scores_and_upserts_same_rows(tmp_path, fakes):
    pool = Pool()
    kwargs = dict(prompts=TRAIN_PROMPTS[:1], checkpoint=tmp_path)
    await module.bootstrap(pool, **kwargs)
    ids = set(pool.rows)
    assert len(fakes) == 8
    await module.bootstrap(pool, **kwargs)
    assert len(fakes) == 8
    assert set(pool.rows) == ids


async def test_single_rung_has_no_cross_ladder_difficulty(fakes):
    pool = Pool()
    await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:1], rungs=MODEL_LADDER[:1])
    assert len(pool.rows) == 1
    assert next(iter(pool.rows.values()))[2] is None


async def test_checkpoint_rejects_changed_prompt(tmp_path, fakes):
    kwargs = dict(checkpoint=tmp_path, rungs=MODEL_LADDER[:1])
    await module.bootstrap(Pool(), prompts=TRAIN_PROMPTS[:1], **kwargs)
    altered = replace(TRAIN_PROMPTS[0], prompt="A different question")
    with pytest.raises(ValueError, match="checkpoint"):
        await module.bootstrap(Pool(), prompts=[altered], **kwargs)


def test_database_name_must_be_isolated():
    for name in ["gatoway", "postgres", 'gatoway_eval_bad";DROP', ""]:
        with pytest.raises(ValueError):
            module.validate_database_name(name)
    module.validate_database_name("gatoway_eval_measured_20260930")


async def test_resume_single_rung_to_full_ladder_fills_difficulty(tmp_path, fakes):
    pool = Pool()
    await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:1], rungs=MODEL_LADDER[:1],
                           checkpoint=tmp_path)
    await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:1], checkpoint=tmp_path)
    assert len(fakes) == 8
    assert len(pool.rows) == 8
    assert all(row[2] == .125 for row in pool.rows.values())


async def test_retry_recovers_without_duplicate_rows(monkeypatch, fakes):
    calls = 0
    async def provider(model, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError()
        return ProviderResponse("answer", model, 1, 2, .1, None)
    monkeypatch.setattr(module, "call_provider", provider)
    pool = Pool()
    await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:1], rungs=MODEL_LADDER[:1])
    assert calls == 2
    assert len(pool.rows) == 1


@pytest.mark.skipif(os.getenv("GATOWAY_DB_TESTS") != "1", reason="opt-in Postgres")
async def test_isolated_postgres_write_and_resume(monkeypatch, tmp_path, fakes):
    import asyncpg
    import uuid
    name = "gatoway_eval_test_" + uuid.uuid4().hex[:12]
    monkeypatch.setattr(module, "embed", lambda text: [1.0] + [0.0] * 383)
    pool = await module.isolated_pool(name)
    try:
        await pool.close()
        # Database comments live in PostgreSQL's shared-object catalog.
        pool = await module.isolated_pool(name)
        await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:2], checkpoint=tmp_path)
        await module.bootstrap(pool, prompts=TRAIN_PROMPTS[:2], checkpoint=tmp_path)
        assert await pool.fetchval("SELECT count(*) FROM decision_history") == 16
        assert await pool.fetchval(
            "SELECT count(*) FROM decision_history WHERE calculated_effectiveness=0"
        ) == 2
        assert await pool.fetchval(
            "SELECT count(*) FROM decision_history WHERE calculated_difficulty=0.125"
        ) == 16
        assert len(fakes) == 16
    finally:
        await pool.close()
        admin = await asyncpg.connect(module.source_database_url())
        try:
            # The name is generated here, and only this test owns this database.
            await admin.execute(f'DROP DATABASE "{name}"')
        finally:
            await admin.close()


async def test_judge_failure_keeps_generated_response_for_retry(monkeypatch, tmp_path, fakes):
    async def broken_judge(*args, **kwargs):
        raise RuntimeError("malformed judge response")
    monkeypatch.setattr(module, "score", broken_judge)
    options = dict(prompts=TRAIN_PROMPTS[:1], rungs=MODEL_LADDER[:1], checkpoint=tmp_path)
    with pytest.raises(RuntimeError, match="malformed"):
        await module.bootstrap(Pool(), **options)
    assert len(fakes) == 1
    async def working_judge(*args, **kwargs):
        return .5
    monkeypatch.setattr(module, "score", working_judge)
    pool = Pool()
    await module.bootstrap(pool, **options)
    assert len(fakes) == 1
    assert next(iter(pool.rows.values()))[3] == .5
