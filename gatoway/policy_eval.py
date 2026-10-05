"""Checkpointed live screening of fixed routing policies against shared outcomes.

Each task/model/repeat is generated once and reused across policies that select
it. Repetitions remain independent. Evaluation labels never enter routing.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import time

from gatoway.bank_corpus import TRAIN_PROMPTS, score
from gatoway.bootstrap_bank import isolated_pool, row_id, save_state
from gatoway.embeddings import embed
from gatoway.breadth_tasks import score_json_normalized
from gatoway.eval import benchmark_tasks, BenchmarkTask
from gatoway.judge import judge
from gatoway.providers import call_provider, RUNG_BY_NAME
from gatoway.reprice_eval import estimate_usd
from gatoway.router import fetch_neighbors, estimate_tokens
from gatoway.routing_policies import POLICIES, select
from gatoway.session import compute_threshold


def tasks():
    result = benchmark_tasks('expanded')
    for name in ('policy_holdout.json', 'downgrade_probes.json'):
        for item in json.loads(Path('benchmarks/breadth', name).read_text()):
            result.append(BenchmarkTask(task_id=item['task_id'], prompt=item['prompt'],
                suite=item['suite'], scoring_method='json_exact', expected=[],
                expected_json=item['answer'], difficulty=0, canned_responses={}))
    return result


def source_hash():
    digest = hashlib.sha256()
    for root in ('gatoway', 'benchmarks'):
        for p in sorted(Path(root).rglob('*')):
            if p.is_file() and '__pycache__' not in str(p):
                digest.update(str(p).encode()); digest.update(p.read_bytes())
    return digest.hexdigest()


async def prepare(args):
    destination = args.output / 'manifest.json'
    if destination.exists():
        manifest = json.loads(destination.read_text())
        if manifest['source_hash'] != source_hash() or manifest['runs'] != args.runs or manifest['prices'] != json.loads(args.prices.read_text()) or manifest['database'] != args.database:
            raise ValueError('Source/config changed; choose a new output directory')
        return manifest
    prices = json.loads(args.prices.read_text())
    pool = await isolated_pool(args.database)
    try:
        rows = await pool.fetch('SELECT row_to_json(d)::text AS row FROM decision_history d ORDER BY routing_id')
        bank_hash = hashlib.sha256(json.dumps([dict(r) for r in rows], sort_keys=True).encode()).hexdigest()
        identities = {str(row_id(p.prompt_id, r.primary)):p.prompt_id
                      for p in TRAIN_PROMPTS for r in RUNG_BY_NAME.values()}
        turns = Counter()
        decisions = {}
        for task in tasks():
            turns[task.suite] += 1
            threshold = compute_threshold(turns[task.suite], 3)
            neighbors = [dict(r) for r in await fetch_neighbors(embed(task.prompt), pool)]
            for n in neighbors:
                n['routing_id'] = str(n['routing_id'])
                n['prompt_id'] = identities[n['routing_id']]
            decisions[task.task_id] = {'suite':task.suite, 'threshold':threshold,
                'neighbors':neighbors, 'policies':{p:select(p, neighbors,
                    estimate_tokens(task.prompt), threshold, prices) for p in POLICIES}}
        manifest = {'source_hash':source_hash(), 'bank_hash':bank_hash, 'bank_rows':len(rows),
                    'database':args.database, 'runs':args.runs, 'prices':prices,
                    'max_tokens':8192, 'temperature':0, 'timeout_seconds':240,
                    'decisions':decisions,
                    'design':'Shared task/model outcomes; existing suite diagnostic, fresh objective holdout screening; no tuning on results.'}
        save_state(destination, manifest)
        return manifest
    finally:
        await pool.close()


def summarize(manifest, state):
    reports = {}
    # Fence-normalized scores (format-tolerant) reported alongside the strict
    # scores. Only json_exact tasks can differ; others reuse the stored score.
    json_expected = {t.task_id: t.expected_json for t in tasks()
                     if t.scoring_method == 'json_exact'}
    def normalized(task, outcome):
        if task in json_expected:
            return score_json_normalized(outcome['response']['content'], json_expected[task])
        return outcome['score']
    for name, suites in [('all', None), ('existing', {'original','coding','structured','reasoning'}),
                          ('holdout', {'holdout_structured','holdout_reasoning'}),
                          ('probe', {'probe_glm5','probe_gemma'})]:
        group = {}
        for policy in POLICIES:
            values=[]; baselines=[]; by_task=defaultdict(list); counts=Counter(); missing=[]
            nvalues=[]; nbaselines=[]; n_by_task=defaultdict(list)
            for task, d in manifest['decisions'].items():
                if suites is not None and d['suite'] not in suites: continue
                for run in range(1, manifest['runs']+1):
                    tier=d['policies'][policy]['tier']
                    key=f'{run}/{task}/{tier}'
                    bkey=f'{run}/{task}/kimi'
                    a,b=state.get(key),state.get(bkey)
                    if not a or 'score' not in a or not b or 'score' not in b:
                        missing.append(key); continue
                    values.append(a); baselines.append(b); counts[tier]+=1
                    by_task[task].append(a['score']-b['score'])
                    na,nb=normalized(task,a),normalized(task,b)
                    nvalues.append(na); nbaselines.append(nb)
                    n_by_task[task].append(na-nb)
            if not values:
                group[policy]={'missing':len(missing)}; continue
            cost=sum(float(a['usd']) for a in values)
            basecost=sum(float(a['usd']) for a in baselines)
            # Cluster bootstrap over task IDs, retaining repeats within each task.
            means=[sum(v)/len(v) for v in by_task.values()]
            rng=random.Random(20261004)
            samples=sorted(sum(rng.choices(means,k=len(means)))/len(means) for _ in range(2000))
            per_suite={}; per_suite_norm={}
            for suite in sorted({d['suite'] for d in manifest['decisions'].values()}):
                ids={t for t,d in manifest['decisions'].items() if d['suite']==suite}
                deltas=[v for t,vs in by_task.items() if t in ids for v in vs]
                ndeltas=[v for t,vs in n_by_task.items() if t in ids for v in vs]
                if deltas: per_suite[suite]=100*sum(deltas)/len(deltas)
                if ndeltas: per_suite_norm[suite]=100*sum(ndeltas)/len(ndeltas)
            group[policy]={'n':len(values),'missing':len(missing),
                'quality':sum(a['score'] for a in values)/len(values),
                'baseline_quality':sum(a['score'] for a in baselines)/len(baselines),
                'quality_delta_points':100*sum(a['score']-b['score'] for a,b in zip(values,baselines))/len(values),
                'delta_ci95_points':[100*samples[49],100*samples[1949]],
                'quality_normalized':sum(nvalues)/len(nvalues),
                'baseline_quality_normalized':sum(nbaselines)/len(nbaselines),
                'quality_delta_normalized_points':100*sum(na-nb for na,nb in zip(nvalues,nbaselines))/len(nvalues),
                'estimated_usd':cost,'baseline_usd':basecost,
                'savings_percent':100*(1-cost/basecost) if basecost else None,
                'provider_seconds':sum(a['seconds'] for a in values),
                'length_finishes':sum(a['response']['finish_reason']=='length' for a in values),
                'model_counts':dict(counts),'suite_delta_points':per_suite,
                'suite_delta_normalized_points':per_suite_norm}
        reports[name]=group
    return reports


async def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    manifest=await prepare(args)
    print('Selections:',json.dumps({p:dict(Counter(d['policies'][p]['tier'] for d in manifest['decisions'].values())) for p in POLICIES}),flush=True)
    if args.prepare_only: return
    path=args.output/'outcomes.json'
    state=json.loads(path.read_text()) if path.exists() else {}
    lock=asyncio.Lock()
    semaphore=asyncio.Semaphore(3)
    async def one(run, task, tier):
        key=f'{run}/{task.task_id}/{tier}'
        async with semaphore:
            if 'score' in state.get(key,{}): return
            record=state.setdefault(key,{})
            try:
                if 'response' not in record:
                    started=time.monotonic()
                    response=await asyncio.wait_for(call_provider(RUNG_BY_NAME[tier].primary,
                        [{'role':'user','content':task.prompt}],temperature=0,max_tokens=8192,
                        allow_reasoning_fallback=False),timeout=240)
                    record['seconds']=time.monotonic()-started
                    record['response']={k:v for k,v in vars(response).items() if k not in ('raw','cost_cents')}
                    record['usd']=str(estimate_usd(record['response'],manifest['prices']))
                    async with lock: save_state(path,state)
                r=record['response']
                if task.scoring_method=='llm_judge':
                    record['score']=await judge(task.prompt,r['content'],task.rubric,r['model_id'],
                                                 audit=record.setdefault('judge_attempts',[]))
                else:
                    record['score']=await score(task,r['content'],r['model_id'])
                record.pop('error',None)
                print(key,record['score'],r['finish_reason'],flush=True)
            except Exception as exc:
                record['error']=type(exc).__name__+': '+str(exc)[:300]
                print(key,'ERROR',record['error'],flush=True)
            finally:
                async with lock: save_state(path,state)
    jobs=[]
    for run in range(1,args.runs+1):
        for task in tasks():
            tiers=sorted({v['tier'] for v in manifest['decisions'][task.task_id]['policies'].values()})
            for tier in tiers: jobs.append((run,task,tier))
    random.Random(20261004).shuffle(jobs)
    print('Unique generation jobs:',len(jobs),flush=True)
    await asyncio.gather(*(one(*job) for job in jobs))
    report=summarize(manifest,state)
    save_state(args.output/'summary.json',report)
    failures=[key for key,value in state.items() if 'score' not in value]
    print('Unresolved:',len(failures),flush=True)
    if failures: raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--database',default='gatoway_eval_measured_20260930')
    parser.add_argument('--prices',type=Path,default=Path('benchmarks/pricing/policy_scenario_20261004.json'))
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--prepare-only',action='store_true')
    asyncio.run(main(parser.parse_args()))
