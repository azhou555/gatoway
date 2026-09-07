"""Thin wrapper around litellm.completion() for the gateway's tier system.

Per SPEC.md §3 ("Provider Adapters") and the non-goal note in §1, we reuse
LiteLLM's provider/response handling rather than rebuilding it. This module
only adds: a tier -> model-list config, a small response dataclass, and a
single async call function.

All tiers are served by NRP (https://nrp.ai/llmtoken/), one OpenAI-compatible
endpoint fronting every NRP-hosted open-weights model, authenticated with
NRP_API_KEY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import litellm
from dotenv import load_dotenv

load_dotenv()

NRP_API_BASE = "https://ellm.nrp-nautilus.io/v1"

# Cost proxy. NRP is free for researchers/educators -- no per-token billing
# and no published price list -- so parameter count (billions, from
# https://nrp.ai/llms/) stands in for price: cents per 1M tokens == params
# in billions. Only the relative ordering matters to the router and the
# spend ledger; the absolute figures are not dollars.
#
# ponytail: flat rate, input and output tokens priced identically. Real
# providers charge 3-5x for output; add that weighting only if NRP ever
# publishes real prices.
#
# NOTE: qwen3 is a 180B-total / 6B-active MoE. We use the headline *total*
# param count, which is what makes it the frontier tier -- costing it by
# active params (6B) would make it cheaper than every other tier and invert
# the whole ladder.
MODEL_PARAMS_B: dict[str, float] = {
    "openai/gemma-small": 12.0,
    "openai/qwen3-small": 27.0,
    "openai/gemma": 31.0,
    "openai/gpt-oss": 120.0,
    "openai/qwen3": 180.0,
}

# Tier -> ordered list of litellm model strings, ordered by parameter count.
# First entry is the primary model for that tier; the second is the fallback
# tried by the circuit breaker on failure (SPEC.md §5: "retry same tier,
# different provider" -- here, a different model of comparable size on a
# different NRP backend).
TIER_MODELS: dict[str, list[str]] = {
    "cheap": ["openai/gemma-small", "openai/qwen3-small"],
    "medium": ["openai/qwen3-small", "openai/gemma"],
    "frontier": ["openai/qwen3", "openai/gpt-oss"],
    # Unwired stub per SPEC.md non-goals / TASKS.md ("Ollama local tier --
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
    finish_reason: str | None = None


def cost_cents(model: str, input_tokens: int, output_tokens: int) -> float:
    """Parameter-count cost proxy for `model`. See MODEL_PARAMS_B."""
    return MODEL_PARAMS_B.get(model, 0.0) * (input_tokens + output_tokens) / 1e6


async def call_provider(model: str, messages: list[dict], **kwargs) -> ProviderResponse:
    """Call a specific litellm model string and return a normalized response.

    Note: takes a concrete model string (e.g. "openai/qwen3-small"), not a
    tier name -- tier -> model resolution and fallback-on-failure is the
    circuit breaker's job (gatoway/circuit_breaker.py).
    """
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        api_base=NRP_API_BASE,
        api_key=os.environ["NRP_API_KEY"],
        **kwargs,
    )

    usage = response.usage
    message = response.choices[0].message
    # Reasoning models (qwen3, gpt-oss, glm-5) can put everything in
    # `reasoning_content` and leave `content` empty; fall back so downstream
    # scoring/embedding never sees None.
    #
    # ponytail: untested path -- every NRP model tried so far fills
    # `content`. If one ever doesn't, this embeds and scores its chain of
    # thought as the answer, corrupting a decision_history row rather than
    # failing loudly. Raise instead of falling back if that shows up.
    content = message.content or getattr(message, "reasoning_content", None) or ""

    return ProviderResponse(
        content=content,
        model_id=model,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cost_cents=cost_cents(model, usage.prompt_tokens, usage.completion_tokens),
        raw=response,
        finish_reason=getattr(response.choices[0], "finish_reason", None),
    )
