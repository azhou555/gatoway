"""Recover unresolved policy outcomes after the main runner has exited.

Keeps request settings fixed; extends only the client deadline to 600 seconds.
Preserves original errors and unknown-usage warnings. Never reruns scored answers.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gatoway.policy_eval import tasks, source_hash, summarize
from gatoway.bank_corpus import score
from gatoway.bootstrap_bank import save_state
from gatoway.judge import judge
from gatoway.providers import call_provider, RUNG_BY_NAME
from gatoway.reprice_eval import estimate_usd


async def main(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest['source_hash']!=source_hash():
        raise ValueError('Sources changed since manifest')
    path=directory/'outcomes.json'
    state=json.loads(path.read_text())
    task_map={t.task_id:t for t in tasks()}
    expected={f'{run}/{task}/{v["tier"]}' for run in range(1,manifest['runs']+1)
              for task,d in manifest['decisions'].items() for v in d['policies'].values()}
    pending=sorted(k for k in expected if 'score' not in state.get(k,{}))
    print('Recovering',len(pending),'unresolved outcomes',flush=True)
    lock=asyncio.Lock(); semaphore=asyncio.Semaphore(3)
    async def one(key):
        async with semaphore:
            record=state.setdefault(key,{})
            run,task_id,tier=key.split('/')
            task=task_map[task_id]
            if 'error' in record:
                record.setdefault('prior_errors',[]).append({'error':record.pop('error'),
                    'stage':'grading' if 'response' in record else 'provider',
                    'usage_unknown':'response' not in record})
            recovery={'started_at':datetime.now(timezone.utc).isoformat(),'timeout_seconds':600}
            record.setdefault('recovery_attempts',[]).append(recovery)
            async with lock: save_state(path,state)
            try:
                if 'response' not in record:
                    started=time.monotonic()
                    response=await asyncio.wait_for(call_provider(RUNG_BY_NAME[tier].primary,
                        [{'role':'user','content':task.prompt}],temperature=manifest['temperature'],
                        max_tokens=manifest['max_tokens'],allow_reasoning_fallback=False),timeout=600)
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
                recovery['status']='ok'
                print(key,record['score'],r['finish_reason'],flush=True)
            except Exception as exc:
                record['error']=type(exc).__name__+': '+str(exc)[:300]
                recovery['status']='error'
                print(key,record['error'],flush=True)
            finally:
                async with lock: save_state(path,state)
    await asyncio.gather(*(one(k) for k in pending))
    save_state(directory/'summary.json',summarize(manifest,state))
    if any('score' not in state.get(k,{}) for k in expected): raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    asyncio.run(main(args.directory))
