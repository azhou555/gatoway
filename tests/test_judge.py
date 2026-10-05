import os

import pytest

import gatoway.judge as module
from gatoway.bank_corpus import TRAIN_PROMPTS
from gatoway.eval import BENCHMARK_TASKS
from gatoway.providers import ProviderResponse


@pytest.mark.parametrize("answer_model,expected", [
    ("openai/kimi", "openai/glm-5"), ("openai/glm-5", "openai/kimi"),
    ("openai/gpt-oss", "openai/kimi"),
])
async def test_model_choice_and_partial_score(monkeypatch, answer_model, expected):
    async def fake(model, messages, **kwargs):
        assert model == expected
        assert kwargs["temperature"] == 0
        assert kwargs["response_format"]["json_schema"]["strict"] is True
        assert kwargs["allow_reasoning_fallback"] is False
        if model == "openai/glm-5":
            assert kwargs["extra_body"]["chat_template_kwargs"]["reasoning_effort"] == "low"
        return ProviderResponse('{"criteria":[true,false]}', model, 0, 0, 0, None)
    monkeypatch.setattr(module, "call_provider", fake)
    assert await module.judge("prompt", "answer", ["one", "two"], answer_model) == .5


@pytest.mark.parametrize("invalid", [
    "not json", '{"criteria":[1]}', '{"criteria":["true"]}',
    '{"criteria":[]}', '{"criteria":true}', '[]', 'null',
])
async def test_malformed_retries_then_raises(monkeypatch, invalid):
    calls = []
    async def fake(model, messages, **kwargs):
        calls.append(model)
        return ProviderResponse(invalid, model, 0, 0, 0, None)
    monkeypatch.setattr(module, "call_provider", fake)
    with pytest.raises(module.JudgeInfrastructureError):
        await module.judge("p", "r", ["criterion"], "openai/gpt-oss")
    assert calls == ["openai/kimi", "openai/kimi"]


async def test_retry_can_recover(monkeypatch):
    answers = iter(["invalid", '{"criteria":[true]}'])
    async def fake(model, *args, **kwargs):
        return ProviderResponse(next(answers), model, 0, 0, 0, None)
    monkeypatch.setattr(module, "call_provider", fake)
    assert await module.judge("p", "r", ["criterion"], "openai/kimi") == 1


async def test_provider_failure_never_substitutes_judge(monkeypatch):
    calls = []
    async def fake(model, *args, **kwargs):
        calls.append(model)
        raise TimeoutError("down")
    monkeypatch.setattr(module, "call_provider", fake)
    with pytest.raises(module.JudgeInfrastructureError):
        await module.judge("p", "r", ["criterion"], "openai/kimi")
    assert calls == ["openai/glm-5", "openai/glm-5"]


@pytest.mark.skipif(os.getenv("GATOWAY_LIVE_TESTS") != "1", reason="opt-in live calibration")
@pytest.mark.parametrize("answer_model", ["openai/kimi", "openai/glm-5"])
@pytest.mark.parametrize(
    "task", [task for task in [*TRAIN_PROMPTS, *BENCHMARK_TASKS]
             if task.scoring_method == "llm_judge"],
    ids=lambda task: getattr(task, "prompt_id", getattr(task, "task_id", "")),
)
async def test_live_rubric_calibration(answer_model, task):
    from gatoway.judge_calibration import cases
    name = getattr(task, "prompt_id", getattr(task, "task_id", ""))
    reference = next(case["answer"] for case in cases() if case["name"] == f"{name}/reference")
    assert await module.judge(task.prompt, reference, task.rubric, answer_model) >= .8
    assert await module.judge(task.prompt, "I don't know.", task.rubric, answer_model) <= .2


async def test_truncated_judge_retry_has_room_for_final_json(monkeypatch):
    budgets = []
    async def fake(model, messages, **kwargs):
        budgets.append(kwargs["max_tokens"])
        if len(budgets) == 1:
            return ProviderResponse("unfinished reasoning", model, 0, 1024, 0, None,
                                    finish_reason="length")
        return ProviderResponse('{"criteria":[true]}', model, 0, 10, 0, None,
                                finish_reason="stop")
    monkeypatch.setattr(module, "call_provider", fake)
    assert await module.judge("p", "r", ["criterion"], "openai/glm-5") == 1
    assert budgets == [1024, 4096]


@pytest.mark.parametrize("invalid", [
    '{"criteria":[true],"extra":1}',
    '{"criteria":[false],"criteria":[true]}',
])
async def test_rejects_extra_or_duplicate_fields(monkeypatch, invalid):
    async def fake(model, *args, **kwargs):
        return ProviderResponse(invalid, model, 0, 0, 0, None)
    monkeypatch.setattr(module, "call_provider", fake)
    with pytest.raises(module.JudgeInfrastructureError):
        await module.judge("p", "r", ["criterion"], "openai/kimi")


async def test_truncation_is_never_a_score_and_retry_has_no_recycled_reasoning(monkeypatch):
    calls = []
    async def fake(model, messages, **kwargs):
        calls.append(list(messages))
        return ProviderResponse('{"criteria":[true]}', model, 0, 1024, 0, None,
                                finish_reason="length")
    monkeypatch.setattr(module, "call_provider", fake)
    audit = []
    with pytest.raises(module.JudgeInfrastructureError):
        await module.judge("p", "r", ["criterion"], "openai/kimi", audit=audit)
    assert calls[0] == calls[1]
    assert len(audit) == 2
    assert all(record["status"] == "error" for record in audit)


async def test_transient_timeout_recovers_with_same_judge(monkeypatch):
    calls = []
    async def fake(model, *args, **kwargs):
        calls.append(model)
        if len(calls) == 1:
            raise TimeoutError("temporary")
        return ProviderResponse('{"criteria":[false]}', model, 0, 10, 0, None,
                                finish_reason="stop")
    monkeypatch.setattr(module, "call_provider", fake)
    audit = []
    assert await module.judge("p", "r", ["criterion"], "openai/kimi", audit=audit) == 0
    assert calls == ["openai/glm-5"] * 2
    assert [r["status"] for r in audit] == ["error", "ok"]
