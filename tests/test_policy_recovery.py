import json
from types import SimpleNamespace

import pytest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("recovery", Path(__file__).resolve().parents[1] / "scripts/recover_policy_eval.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


@pytest.mark.asyncio
async def test_recovery_reuses_saved_answer_and_preserves_error(tmp_path, monkeypatch):
    manifest={'source_hash':'same','runs':1,'decisions':{
        'task':{'policies':{'test':{'tier':'kimi'}}}},'prices':{}}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    response={'model_id':'openai/kimi','content':'saved answer','finish_reason':'stop'}
    (tmp_path/'outcomes.json').write_text(json.dumps({'1/task/kimi':{
        'response':response,'usd':'.01','seconds':1,'error':'JudgeInfrastructureError: old'}}))
    monkeypatch.setattr(recovery,'source_hash',lambda:'same')
    monkeypatch.setattr(recovery,'tasks',lambda:[SimpleNamespace(task_id='task',scoring_method='json_exact')])
    monkeypatch.setattr(recovery,'summarize',lambda m,s:{})
    async def provider(*args,**kwargs):
        pytest.fail('Saved answer must not be regenerated')
    async def score(task,content,model):
        assert content=='saved answer'
        return 1
    monkeypatch.setattr(recovery,'call_provider',provider)
    monkeypatch.setattr(recovery,'score',score)
    await recovery.main(tmp_path)
    record=json.loads((tmp_path/'outcomes.json').read_text())['1/task/kimi']
    assert record['score']==1
    assert 'error' not in record
    assert record['prior_errors'][0]['stage']=='grading'
    assert record['prior_errors'][0]['usage_unknown'] is False
    await recovery.main(tmp_path)
    assert len(json.loads((tmp_path/'outcomes.json').read_text())['1/task/kimi']['recovery_attempts'])==1


@pytest.mark.asyncio
async def test_recovery_rejects_source_change(tmp_path,monkeypatch):
    (tmp_path/'manifest.json').write_text(json.dumps({'source_hash':'old'}))
    monkeypatch.setattr(recovery,'source_hash',lambda:'new')
    with pytest.raises(ValueError,match='Sources changed'):
        await recovery.main(tmp_path)
