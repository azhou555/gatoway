"""Thin wrapper around litellm.completion() for the gateway's tier system.

Per SPEC.md §3 ("Provider Adapters") and the non-goal note in §1, we reuse
LiteLLM's provider/response handling rather than rebuilding it. This module
only adds: a tier -> model-list config, a small response dataclass, and a
single async call function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import litellm

# Tier -> ordered list of litellm model strings. First entry is the primary
# provider for that tier; any additional entries are fallback providers tried
# by the circuit breaker on failure (SPEC.md §5: "retry same tier, different
# provider").
TIER_MODELS: dict[str, list[str]] = {
    "cheap": ["anthropic/claude-haiku-4-5-20251001"],
    "medium": ["anthropic/claude-sonnet-4-5"],
    "frontier": ["anthropic/claude-opus-4-5"],
    # Unwired stub per SPEC.md non-goals / TASKS.md ("Ollama local tier —
    # stub adapter only, not wired into router by default"). Not referenced
    # by TIER_MODELS lookups elsewhere; kept separate so it can't
    # accidentally get called by the router/circuit breaker.
    "ollama": ["ollama/llama3"],
}


@dataclass
class ProviderResponse:
    content: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_cents: float
    raw: Any = field(repr=False)


async def call_provider(model: str, messages: list[dict], **kwargs) -> ProviderResponse:
    """Call a specific litellm model string and return a normalized response.

    Note: takes a concrete model string (e.g. "anthropic/claude-sonnet-4-5"),
    not a tier name — tier -> model resolution and fallback-on-failure is the
    circuit breaker's job (gatoway/circuit_breaker.py).
    """
    response = await litellm.acompletion(model=model, messages=messages, **kwargs)

    usage = response.usage
    try:
        cost_usd = litellm.completion_cost(completion_response=response)
    except Exception:
        cost_usd = 0.0

    return ProviderResponse(
        content=response.choices[0].message.content,
        model_id=model,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cost_cents=cost_usd * 100,
        raw=response,
    )
