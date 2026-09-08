"""Thin wrapper around litellm.completion() for the gateway's model ladder.

Per SPEC.md §3 ("Provider Adapters") and the non-goal note in §1, we reuse
LiteLLM's provider/response handling rather than rebuilding it. This module
only adds: an ordered rung config, a small response dataclass, and a
single async call function.

All rungs are served by NRP (https://nrp.ai/llmtoken/), one OpenAI-compatible
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
# NOTE: several entries are MoE models. We use headline *total* parameters
# consistently because NRP does not publish active-parameter counts for the
# full inventory. This is an explicit proxy, not a claim about inference cost.
MODEL_PARAMS_B: dict[str, float] = {
    "openai/gemma-small": 12.0,
    "openai/qwen3-small": 27.0,
    "openai/gemma": 31.0,
    "openai/gpt-oss": 120.0,
    "openai/qwen3": 180.0,
    "openai/minimax-m2": 230.0,
    "openai/deepseek-v4-flash": 304.0,
    "openai/glm-5": 753.0,
    "openai/kimi": 1000.0,
}

# Context capacities are model-specific hard routing constraints. Values are
# from NRP's managed-model matrix; its `/v1/models` endpoint does not expose
# this metadata. Keep fallbacks here too because a
# fallback may have a different window than its rung's primary.
MODEL_CONTEXT_TOKENS: dict[str, int] = {
    "openai/gemma-small": 262_144,
    "openai/qwen3-small": 1_000_000,
    "openai/gemma": 262_144,
    "openai/gpt-oss": 131_072,
    "openai/qwen3": 1_000_000,
    "openai/minimax-m2": 204_800,
    "openai/deepseek-v4-flash": 1_048_576,
    "openai/glm-5": 1_048_576,
    "openai/kimi": 131_072,
}


@dataclass(frozen=True)
class ModelRung:
    """One selectable ladder position and its provider fallback order."""

    name: str
    models: tuple[str, ...]

    @property
    def primary(self) -> str:
        return self.models[0]

    @property
    def params_b(self) -> float:
        return MODEL_PARAMS_B[self.primary]

    @property
    def context_tokens(self) -> int:
        return MODEL_CONTEXT_TOKENS[self.primary]


# Ascending by the only consistently available cost signal: total params.
# Neighboring rungs cross-fallback where NRP has no same-size duplicate.
# gemma-small-e4b stays out because NRP's active-model matrix no longer lists
# that compatibility endpoint.
MODEL_LADDER: tuple[ModelRung, ...] = (
    ModelRung("gemma-small", ("openai/gemma-small", "openai/qwen3-small")),
    ModelRung("qwen3-small", ("openai/qwen3-small", "openai/gemma")),
    ModelRung("gpt-oss", ("openai/gpt-oss", "openai/qwen3")),
    ModelRung("qwen3", ("openai/qwen3", "openai/gpt-oss")),
    ModelRung("minimax-m2", ("openai/minimax-m2", "openai/deepseek-v4-flash")),
    ModelRung("deepseek-v4-flash", ("openai/deepseek-v4-flash", "openai/minimax-m2")),
    ModelRung("glm-5", ("openai/glm-5", "openai/kimi")),
    ModelRung("kimi", ("openai/kimi", "openai/glm-5")),
)

RUNG_NAMES: tuple[str, ...] = tuple(rung.name for rung in MODEL_LADDER)
RUNG_BY_NAME: dict[str, ModelRung] = {rung.name: rung for rung in MODEL_LADDER}

# Compatibility name retained for callers while their public `tier` fields
# transition to rung names. Unlike the old mapping, every key is selectable.
TIER_MODELS: dict[str, list[str]] = {
    rung.name: list(rung.models) for rung in MODEL_LADDER
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
    rung name -- rung -> model resolution and fallback-on-failure is the
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
