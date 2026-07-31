"""Tests for the provider-failure branch of SPEC.md §5's fallback state
machine: 3 consecutive failures -> cooldown -> calls rejected during cooldown
-> recovery after cooldown expires.

Uses a fake provider function (monkeypatched onto
gatoway.circuit_breaker.call_provider) so no real API calls happen.
"""

from __future__ import annotations

import pytest

from gatoway import circuit_breaker as cb_module
from gatoway.circuit_breaker import CircuitBreaker, TierInCooldownError
from gatoway.providers import ProviderResponse

TIER_MODELS = {"cheap": ["fake/model-a", "fake/model-b"]}


def make_fake_provider(fail_models: set[str]):
    """Returns a fake `call_provider` coroutine that raises for any model in
    `fail_models` and otherwise returns a stub success response."""

    async def fake_call_provider(model, messages, **kwargs):
        if model in fail_models:
            raise RuntimeError(f"simulated failure for {model}")
        return ProviderResponse(
            content="ok",
            model_id=model,
            input_tokens=1,
            output_tokens=1,
            cost_cents=0.01,
            raw=None,
        )

    return fake_call_provider


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_single_failure_retries_other_provider_and_succeeds(monkeypatch):
    # Primary model fails, fallback model in the tier succeeds -> overall
    # call succeeds, no cooldown tripped.
    fake = make_fake_provider(fail_models={"fake/model-a"})
    monkeypatch.setattr(cb_module, "call_provider", fake)

    breaker = CircuitBreaker(tier_models=TIER_MODELS, cooldown_seconds=60.0)
    response = await breaker.call("cheap", [{"role": "user", "content": "hi"}])
    assert response.model_id == "fake/model-b"


@pytest.mark.asyncio
async def test_three_consecutive_failures_trips_cooldown(monkeypatch):
    # Both providers in the tier always fail -> every breaker.call() attempt
    # is one "consecutive failure" toward the threshold.
    fake = make_fake_provider(fail_models={"fake/model-a", "fake/model-b"})
    monkeypatch.setattr(cb_module, "call_provider", fake)

    clock = FakeClock()
    breaker = CircuitBreaker(
        tier_models=TIER_MODELS, cooldown_seconds=60.0, time_fn=clock
    )

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call("cheap", [{"role": "user", "content": "hi"}])

    # 4th call should be short-circuited by cooldown, not hit the provider.
    with pytest.raises(TierInCooldownError):
        await breaker.call("cheap", [{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_calls_during_cooldown_are_rejected_without_calling_provider(
    monkeypatch,
):
    call_count = 0

    async def counting_fail(model, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(cb_module, "call_provider", counting_fail)

    clock = FakeClock()
    breaker = CircuitBreaker(
        tier_models=TIER_MODELS, cooldown_seconds=60.0, time_fn=clock
    )

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call("cheap", [{"role": "user", "content": "hi"}])

    calls_before = call_count
    with pytest.raises(TierInCooldownError):
        await breaker.call("cheap", [{"role": "user", "content": "hi"}])
    # The provider must not have been invoked while in cooldown.
    assert call_count == calls_before


@pytest.mark.asyncio
async def test_recovers_after_cooldown_expires(monkeypatch):
    fail_models = {"fake/model-a", "fake/model-b"}
    fake = make_fake_provider(fail_models=fail_models)
    monkeypatch.setattr(cb_module, "call_provider", fake)

    clock = FakeClock()
    breaker = CircuitBreaker(
        tier_models=TIER_MODELS, cooldown_seconds=60.0, time_fn=clock
    )

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call("cheap", [{"role": "user", "content": "hi"}])

    with pytest.raises(TierInCooldownError):
        await breaker.call("cheap", [{"role": "user", "content": "hi"}])

    # Advance the fake clock past the cooldown window.
    clock.advance(60.01)

    # Now make the provider succeed and confirm the breaker allows the call
    # through and resets failure state.
    fail_models.clear()
    response = await breaker.call("cheap", [{"role": "user", "content": "hi"}])
    assert response.model_id == "fake/model-a"

    state = breaker._state_for("cheap")
    assert state.consecutive_failures == 0
    assert state.cooldown_until is None
