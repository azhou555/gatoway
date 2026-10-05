import itertools
import json

import pytest

from gatoway.breadth_tasks import load_cases, score_json
from gatoway.eval import benchmark_tasks, run_eval_repeated, build_report, stability_gate
from gatoway.bank_corpus import TRAIN_PROMPTS, assert_no_eval_overlap, score


@pytest.mark.parametrize('case', load_cases(), ids=lambda case: case['task_id'])
async def test_gold_and_wrong_answers(case):
    task = next(t for t in benchmark_tasks('expanded') if t.task_id == case['task_id'])
    assert await score(task, json.dumps(case['answer']), 'unused') == 1
    for wrong in ['null', 'true', '{}', '[]', 'I cannot answer.', '```json\n'+json.dumps(case['answer'])+'\n```']:
        assert await score(task, wrong, 'unused') == 0


@pytest.mark.parametrize('response,expected', [
    ('{"x":true}', {'x':1}), ('{"x":1}', {'x':True}),
    ('{"x":1,"x":2}', {'x':2}), ('{"x":1,"extra":0}', {'x':1}),
    ('[2,1]', [1,2]), ('{"x":NaN}', {'x':None}),
    ('{"x":Infinity}', {'x':None}), ('prefix {"x":1}', {'x':1}),
    ('{"x":1} trailing', {'x':1}),
])
def test_strict_json_rejects_false_positives(response, expected):
    assert score_json(response, expected) == 0


def test_json_accepts_key_reordering_and_numeric_equivalence():
    assert score_json('{"b": null, "a": 1.0}', {'a':1,'b':None}) == 1


def test_breadth_is_separate_and_held_out():
    old, new = benchmark_tasks(), benchmark_tasks('expanded')
    assert len(old) == 16 and len(new) == 32
    assert new[:16] == old
    assert len({t.task_id for t in new}) == 32
    assert all(t.split == 'eval' for t in new)
    assert_no_eval_overlap(TRAIN_PROMPTS)
    assert not {t.task_id for t in new} & {t.prompt_id for t in TRAIN_PROMPTS}
    with pytest.raises(AssertionError, match='invoice_extraction'):
        assert_no_eval_overlap([new[16].prompt])


def test_constraint_and_arithmetic_references_independently():
    answers = {c['task_id']:c['answer'] for c in load_cases()}
    orders = [list(p) for p in itertools.permutations('ABCD')
              if p.index('A') < p.index('C') and p.index('B') == p.index('A')+1
              and p.index('D') < p.index('A')]
    assert orders == [answers['schedule_constraints']]
    jobs = [('A',4,7),('B',3,6),('C',2,5),('D',5,9)]
    feasible = [subset for n in range(5) for subset in itertools.combinations(jobs,n)
                if sum(j[1] for j in subset) <= 7]
    best = max(feasible, key=lambda subset:sum(j[2] for j in subset))
    assert answers['capacity_planning'] == {'jobs':[j[0] for j in best], 'value':sum(j[2] for j in best)}
    assert answers['discount_tax']['total_cents'] == 3*1250*80//100*108//100+500
    assert answers['weighted_average']['mean'] == (2*10+6*20)/8


async def test_expanded_sessions_report_and_gate():
    tasks = benchmark_tasks('expanded')
    runs = await run_eval_repeated(True, None, 3, tasks=tasks)
    assert len(runs[0].router_results) == 32
    for name in ['original','coding','structured','reasoning']:
        rows = [r for r in runs[0].router_results if r.suite == name]
        assert len(rows) == 8
        assert rows[0].current_threshold == .5
    assert stability_gate(runs, tasks)[0]
    report = build_report(runs, True, tasks=tasks)
    assert 'four independent eight-turn sessions' in report
    assert '| structured |' in report and '| reasoning |' in report
    runs[-1].router_results[-1].score = 0
    assert 'long_context_override' in stability_gate(runs, tasks)[1]
