"""Tests for gatoway/app.py (Subtask 4: Gateway API integration layer).

Uses FastAPI's TestClient with the DB pool, embedding model, router, and
provider/breaker calls all monkeypatched -- no live Postgres or provider API
keys required. Covers the three branches of SPEC.md §5's fallback state
machine as seen from the HTTP layer:

  1. Happy path: classify() succeeds, breaker.call() succeeds -> 200 with
     the OpenAI-compatible shape + gatoway metadata.
  2. Classifier failure: classify() raises -> call_with_classifier_fallback()
     used instead (medium tier, no breaker), reported as classifier_failed.
  3. Circuit breaker exhausted: classify() succeeds but breaker.call() raises
     TierInCooldownError -> clean 503 in OpenAI error shape, not a 500.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import gatoway.app as app_module
from gatoway.circuit_breaker import TierInCooldownError
from gatoway.providers import ProviderResponse
from gatoway.router import RoutingDecision


class FakePool:
    """Minimal asyncpg.Pool stand-in: records execute() calls, has no rows
    to return for fetchrow() (tests only exercise new-session requests, so
    SessionTracker.start_session -- execute only -- is what's exercised).
    """

    def __init__(self):
        self.executed: list[tuple] = []

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def fetchrow(self, query, *args):
        return None


FAKE_EMBEDDING = [0.1] * 384


@pytest.fixture(autouse=True)
def fake_pool(monkeypatch):
    pool = FakePool()

    async def fake_get_pool():
        return pool

    monkeypatch.setattr(app_module, "get_pool", fake_get_pool)
    monkeypatch.setattr(app_module, "embed", lambda text: list(FAKE_EMBEDDING))
    # Fresh breaker per test so cooldown state from one test can't leak into
    # another (breaker is a process-wide singleton in app.py).
    monkeypatch.setattr(app_module, "breaker", app_module.CircuitBreaker())
    return pool


@pytest.fixture
def client():
    return TestClient(app_module.app)


def make_provider_response(model_id="anthropic/claude-sonnet-4-5"):
    return ProviderResponse(
        content="4",
        model_id=model_id,
        input_tokens=10,
        output_tokens=2,
        cost_cents=0.05,
        raw=None,
    )


def test_happy_path_returns_200_with_gatoway_metadata(monkeypatch):
    decision = RoutingDecision(
        tier="cheap",
        confidence=0.9,
        low_confidence=False,
        calculated_difficulty=0.1,
        matched_routing_id=uuid.uuid4(),
        input_embedding=FAKE_EMBEDDING,
    )

    async def fake_classify(text, pool, current_threshold):
        return decision

    async def fake_breaker_call(self, tier, messages, **kwargs):
        assert tier == "cheap"
        return make_provider_response("anthropic/claude-haiku-4-5-20251001")

    monkeypatch.setattr(app_module, "classify", fake_classify)
    monkeypatch.setattr(app_module.CircuitBreaker, "call", fake_breaker_call)
    # Rebuild breaker so the patched .call is picked up via the class.
    monkeypatch.setattr(app_module, "breaker", app_module.CircuitBreaker())

    client = TestClient(app_module.app)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "what is 2+2?"}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "4"
    assert body["usage"]["total_tokens"] == 12
    assert body["gatoway"]["tier"] == "cheap"
    assert body["gatoway"]["model_id"] == "anthropic/claude-haiku-4-5-20251001"
    assert body["gatoway"]["classifier_failed"] is False
    assert body["gatoway"]["confidence"] == 0.9
    assert "session_id" in body["gatoway"]


def test_classifier_failure_falls_back_to_medium_tier(monkeypatch, fake_pool):
    async def fake_classify(text, pool, current_threshold):
        raise RuntimeError("embedding service unreachable")

    async def fake_fallback(messages, **kwargs):
        return make_provider_response("anthropic/claude-sonnet-4-5")

    breaker_call_invoked = False

    async def fake_breaker_call(self, tier, messages, **kwargs):
        nonlocal breaker_call_invoked
        breaker_call_invoked = True
        raise AssertionError("breaker.call must not be used on classifier failure")

    monkeypatch.setattr(app_module, "classify", fake_classify)
    monkeypatch.setattr(app_module, "call_with_classifier_fallback", fake_fallback)
    monkeypatch.setattr(app_module.CircuitBreaker, "call", fake_breaker_call)
    monkeypatch.setattr(app_module, "breaker", app_module.CircuitBreaker())

    client = TestClient(app_module.app)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "help me debug this"}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert breaker_call_invoked is False
    assert body["gatoway"]["classifier_failed"] is True
    assert body["gatoway"]["tier"] == "medium"
    assert body["gatoway"]["model_id"] == "anthropic/claude-sonnet-4-5"
    assert body["gatoway"]["confidence"] is None


def test_circuit_breaker_exhausted_returns_clean_503(monkeypatch, fake_pool):
    decision = RoutingDecision(
        tier="frontier",
        confidence=0.8,
        low_confidence=False,
        calculated_difficulty=0.9,
        matched_routing_id=uuid.uuid4(),
        input_embedding=FAKE_EMBEDDING,
    )

    async def fake_classify(text, pool, current_threshold):
        return decision

    async def fake_breaker_call(self, tier, messages, **kwargs):
        raise TierInCooldownError(tier, 42.0)

    monkeypatch.setattr(app_module, "classify", fake_classify)
    monkeypatch.setattr(app_module.CircuitBreaker, "call", fake_breaker_call)
    monkeypatch.setattr(app_module, "breaker", app_module.CircuitBreaker())

    client = TestClient(app_module.app)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "prove the riemann hypothesis"}]},
    )

    assert resp.status_code == 503
    body = resp.json()
    assert "error" in body
    assert "frontier" in body["error"]["message"]
    # No decision_history row should have been written for a failed call.
    assert not any("INSERT INTO decision_history" in q for q, _ in fake_pool.executed)
