import json
from pathlib import Path

from gatoway.routing_policies import select
from gatoway.policy_eval import tasks, summarize

PRICES=json.loads(Path('benchmarks/pricing/policy_scenario_20261004.json').read_text())


def neighbors(model, scores, similarity=.5, ids=('a','b','c')):
    return [dict(routing_id=f'{model}/{i}',prompt_id=i,model_id='openai/'+model,
                 calculated_effectiveness=s,calculated_difficulty=.5,similarity=similarity)
            for i,s in zip(ids,scores)]


def pick(policy, rows):
    return select(policy,rows,100,.5,PRICES)['tier']


def test_frontier_fallback_changes_only_weak_evidence():
    assert pick('current',[])=='gpt-oss'
    assert pick('frontier_fallback',[])=='kimi'
    rows=neighbors('gemma-small',[1,1,1])
    assert pick('frontier_fallback',rows)=='gemma-small'


def test_paired_uses_same_prompts_and_rejects_quality_loss():
    good=neighbors('gemma-small',[1,1,1])
    assert pick('paired_quality',good)=='kimi'
    assert pick('paired_quality',good+neighbors('kimi',[1,1,1]))=='gemma-small'
    assert pick('paired_quality',good+neighbors('kimi',[1,1,1],ids=('x','y','z')))=='kimi'
    assert pick('paired_quality',neighbors('gemma-small',[1,1,.5])+neighbors('kimi',[1,1,1]))=='kimi'


def test_price_order_uses_rates_not_parameters():
    rows=neighbors('gemma-small',[1,1,1])+neighbors('gpt-oss',[1,1,1])
    assert pick('current',rows)=='gemma-small'
    assert pick('price_order',rows)=='gpt-oss'


def test_strict_requires_more_similar_successes():
    assert pick('strict_evidence',neighbors('gemma-small',[1,1,1],.35))=='kimi'
    assert pick('strict_evidence',neighbors('gemma-small',[1,1,.9]))=='kimi'
    assert pick('strict_evidence',neighbors('gemma-small',[1,1,1]))=='gemma-small'


def test_paired_price_rejects_individual_regret_even_if_average_ties():
    rows=neighbors('gemma-small',[1,1,.5])+neighbors('kimi',[.5,1,1])
    assert pick('paired_quality',rows)=='gemma-small'
    assert pick('paired_price',rows)=='kimi'


def test_holdout_separate_and_objectively_scored():
    all_tasks=tasks()
    assert len({t.task_id for t in all_tasks})==78  # 48 screening + 30 downgrade probes
    held=[t for t in all_tasks if t.suite.startswith('holdout')]
    assert len(held)==16
    probes=[t for t in all_tasks if t.suite.startswith('probe_')]
    assert len(probes)==30
    assert {t.suite for t in probes}=={'probe_glm5','probe_gemma'}
    from gatoway.breadth_tasks import score_json
    for task in held+probes:
        assert task.scoring_method=='json_exact'
        assert score_json(json.dumps(task.expected_json),task.expected_json)==1


def test_summary_shared_outcomes_and_missing_pairs():
    from gatoway.routing_policies import POLICIES
    manifest={'runs':3,'decisions':{'one':{'suite':'holdout_reasoning','policies':{
        p:{'tier':'kimi' if p=='always_kimi' else 'gpt-oss'} for p in POLICIES}}}}
    def outcome(value,cost):
        return {'score':value,'usd':str(cost),'seconds':2,'response':{'finish_reason':'stop'}}
    state={f'{r}/one/kimi':outcome(1,.01) for r in range(1,4)}
    state.update({f'{r}/one/gpt-oss':outcome(.5,.001) for r in range(1,3)})
    result=summarize(manifest,state)['holdout']['current']
    assert result['missing']==1
    assert result['n']==2
    assert result['quality_delta_points']==-50
    assert result['delta_ci95_points']==[-50,-50]
    assert result['savings_percent']==90


def test_assumed_price_preserves_provenance_and_unknown_stays_unknown():
    from gatoway.reprice_eval import compare, estimate_usd
    from decimal import Decimal
    response={'model_id':'openai/gemma-small','input_tokens':1000000,'output_tokens':1000000}
    assert estimate_usd(response,PRICES)==Decimal('.53')
    checkpoint={'signature':'test','responses':{'one/router/small':response,'one/baseline/large':response}}
    assert compare([checkpoint],PRICES)['basis']=='mixed_list_prices_with_user_assumed_gemma_rate'
    assert estimate_usd(dict(response,model_id='unknown'),PRICES) is None
