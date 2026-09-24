"""Cost proxy + tier ladder (gatoway/providers.py).

Offline: no network. The live per-model smoke check (every configured NRP
model answers, non-empty content, cost > 0) is a manual run, not part of the
suite -- it costs real latency and needs NRP_API_KEY.
"""

from gatoway.providers import (
    MODEL_CONTEXT_TOKENS,
    MODEL_LADDER,
    MODEL_PARAMS_B,
    RUNG_NAMES,
    TIER_MODELS,
    cost_cents,
)


def test_cost_scales_with_params_and_tokens():
    # cents per 1M tokens == params in billions, flat across in/out tokens.
    assert cost_cents("openai/qwen3", 500_000, 500_000) == 180.0
    assert cost_cents("openai/gemma-small", 500_000, 500_000) == 12.0
    assert cost_cents("openai/qwen3", 0, 0) == 0.0


def test_unknown_model_costs_zero_not_crash():
    assert cost_cents("ollama/llama3", 100, 100) == 0.0


def test_tier_ladder_ascends_by_param_count():
    params = [rung.params_b for rung in MODEL_LADDER]
    assert params == sorted(params) and len(set(params)) == len(params)


def test_every_routable_model_is_priced():
    assert len(MODEL_LADDER) == 8
    assert tuple(TIER_MODELS) == RUNG_NAMES
    for rung in MODEL_LADDER:
        assert len(TIER_MODELS[rung.name]) == 2, "breaker retries a 2nd model"
        for model in TIER_MODELS[rung.name]:
            assert model in MODEL_PARAMS_B, f"{model} has no cost proxy"
            assert model in MODEL_CONTEXT_TOKENS, f"{model} has no context limit"


def test_every_characterized_candidate_is_reachable_without_alias_rungs():
    configured = {model for models in TIER_MODELS.values() for model in models}

    assert configured == {
        "openai/gemma-small",
        "openai/qwen3-small",
        "openai/gemma",
        "openai/gpt-oss",
        "openai/qwen3",
        "openai/minimax-m2",
        "openai/deepseek-v4-flash",
        "openai/glm-5",
        "openai/kimi",
    }
    assert len({rung.primary for rung in MODEL_LADDER}) == len(MODEL_LADDER)
