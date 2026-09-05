"""Cost proxy + tier ladder (gatoway/providers.py).

Offline: no network. The live per-model smoke check (every configured NRP
model answers, non-empty content, cost > 0) is a manual run, not part of the
suite -- it costs real latency and needs NRP_API_KEY.
"""

from gatoway.providers import MODEL_PARAMS_B, TIER_MODELS, cost_cents


def test_cost_scales_with_params_and_tokens():
    # cents per 1M tokens == params in billions, flat across in/out tokens.
    assert cost_cents("openai/qwen3", 500_000, 500_000) == 180.0
    assert cost_cents("openai/gemma-small", 500_000, 500_000) == 12.0
    assert cost_cents("openai/qwen3", 0, 0) == 0.0


def test_unknown_model_costs_zero_not_crash():
    assert cost_cents("ollama/llama3", 100, 100) == 0.0


def test_tier_ladder_ascends_by_param_count():
    tiers = ["cheap", "medium", "frontier"]
    params = [MODEL_PARAMS_B[TIER_MODELS[t][0]] for t in tiers]
    assert params == sorted(params) and len(set(params)) == len(params)


def test_every_routable_model_is_priced():
    for tier in ("cheap", "medium", "frontier"):
        assert len(TIER_MODELS[tier]) == 2, "circuit breaker retries a 2nd model"
        for model in TIER_MODELS[tier]:
            assert model in MODEL_PARAMS_B, f"{model} has no cost proxy"
