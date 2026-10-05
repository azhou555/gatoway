import json

import pytest

import gatoway.judge_calibration as module


def test_calibration_includes_partial_injection_and_historical_failure():
    cases = module.cases()
    assert len(cases) == 27
    indexed = {case['name']:case for case in cases}
    assert indexed['auth_extraction/partial']['low'] == .4
    assert indexed['auth_extraction/injection']['high'] == 0
    assert indexed['auth_extraction/truncated_regression']['semantic_check'] is False


def test_migration_calibration_anchor_covers_missing_rubric_details():
    from gatoway.eval import BENCHMARK_TASKS
    case = next(c for c in module.cases() if c['name'] == 'multistep_planning/reference')
    task = next(t for t in BENCHMARK_TASKS if t.task_id == 'multistep_planning')
    assert case['answer'] != task.reference_response
    assert 'same transaction' in case['answer']
    assert 'Before switching' in case['answer']


async def test_unknown_case_does_not_create_a_record(tmp_path):
    path = tmp_path/'record.json'
    with pytest.raises(ValueError, match='Unknown calibration'):
        await module.calibrate(1, path, case_names=['typo'])
    assert not path.exists()


async def test_calibration_records_failure_and_continues_without_overwriting(monkeypatch, tmp_path):
    cases = module.cases()[-2:]
    monkeypatch.setattr(module, 'cases', lambda:cases)
    calls = 0
    async def fake(*args, audit, **kwargs):
        nonlocal calls
        calls += 1
        audit.append({'status':'error' if calls == 1 else 'ok', 'seconds':.1})
        if calls == 1:
            raise module.JudgeInfrastructureError('provider failed')
        return 0.0
    monkeypatch.setattr(module, 'judge', fake)
    path = tmp_path/'record.json'
    assert not await module.calibrate(1, path)
    saved = path.read_text()
    record = json.loads(saved)
    assert record['complete']
    assert record['summary']['infrastructure_failures'] == 1
    assert len(record['results']) == 4
    with pytest.raises(FileExistsError):
        await module.calibrate(1, path)
    assert path.read_text() == saved
