"""Fallback state machine from SPEC.md §5 (provider-failure branch) plus the
classifier-failure helper.

Two independent paths, per the spec's state diagram:

- Provider failure: CallProvider -> ProviderFailed -> RetrySameTierDifferentProvider
  -> (Success | ProviderFailed). 3 consecutive failures for a tier ->
  MarkUnhealthy -> Cooldown60s -> Routing (retry allowed again).
- Classifier failure: bypasses the breaker entirely, single request to the
  medium tier ("UseMediumTier: default to Sonnet, single request, no breaker").

State is in-process (dict + lock) per TASKS.md: single gateway instance, no
Redis for MVP.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from gatoway.providers import TIER_MODELS, ProviderResponse, call_provider

FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 60.0


class TierInCooldownError(Exception):
    """Raised when a tier is unhealthy and still within its cooldown window."""

    def __init__(self, tier: str, retry_after: float):
        self.tier = tier
        self.retry_after = retry_after
        super().__init__(
            f"tier '{tier}' is in cooldown for another {retry_after:.1f}s"
        )


@dataclass
class _TierState:
    consecutive_failures: int = 0
    cooldown_until: float | None = None


class CircuitBreaker:
    """Per-tier consecutive-failure tracking with a cooldown window.

    `cooldown_seconds` and `time_fn` are injectable so tests don't need to
    sleep for 60 real seconds.
    """

    def __init__(
        self,
        tier_models: dict[str, list[str]] | None = None,
        failure_threshold: int = FAILURE_THRESHOLD,
        cooldown_seconds: float = COOLDOWN_SECONDS,
        time_fn=time.monotonic,
    ):
        self._tier_models = tier_models if tier_models is not None else TIER_MODELS
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._time_fn = time_fn
        self._lock = asyncio.Lock()
        self._state: dict[str, _TierState] = {}

    def _state_for(self, tier: str) -> _TierState:
        return self._state.setdefault(tier, _TierState())

    async def _check_cooldown(self, tier: str) -> None:
        async with self._lock:
            state = self._state_for(tier)
            if state.cooldown_until is not None:
                now = self._time_fn()
                if now < state.cooldown_until:
                    raise TierInCooldownError(tier, state.cooldown_until - now)
                # Cooldown expired: allow a fresh attempt (simple half-open —
                # next call's outcome decides success/re-trip below).
                state.cooldown_until = None
                state.consecutive_failures = 0

    async def _record_success(self, tier: str) -> None:
        async with self._lock:
            state = self._state_for(tier)
            state.consecutive_failures = 0
            state.cooldown_until = None

    async def _record_failure(self, tier: str) -> None:
        async with self._lock:
            state = self._state_for(tier)
            state.consecutive_failures += 1
            if state.consecutive_failures >= self._failure_threshold:
                state.cooldown_until = self._time_fn() + self._cooldown_seconds

    async def call(
        self, tier: str, messages: list[dict], **kwargs
    ) -> ProviderResponse:
        """Call `tier`, retrying once with a different provider on failure.

        Raises TierInCooldownError if the tier is currently unhealthy.
        Raises the last provider exception if all candidates for this
        attempt fail (that failure still counts toward the tier's
        consecutive-failure total).
        """
        await self._check_cooldown(tier)

        candidates = self._tier_models[tier]
        last_exc: Exception | None = None
        for model in candidates[:2]:  # primary + one fallback provider
            try:
                response = await call_provider(model, messages, **kwargs)
            except Exception as exc:  # noqa: BLE001 - provider errors are opaque
                last_exc = exc
                continue
            else:
                await self._record_success(tier)
                return response

        await self._record_failure(tier)
        assert last_exc is not None
        raise last_exc


async def call_with_classifier_fallback(
    messages: list[dict], **kwargs
) -> ProviderResponse:
    """Classifier/router failed (e.g. embedding lookup errored) -> default
    straight to the medium tier for a single request, bypassing the circuit
    breaker entirely (SPEC.md §5: "no breaker").
    """
    model = TIER_MODELS["medium"][0]
    return await call_provider(model, messages, **kwargs)
