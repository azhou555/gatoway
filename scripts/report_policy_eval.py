"""Render a completed or explicitly partial policy screening checkpoint."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gatoway.policy_eval import summarize, tasks

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
manifest=json.loads((args.directory/'manifest.json').read_text())
state=json.loads((args.directory/'outcomes.json').read_text())
summary=summarize(manifest,state)
# Only tasks present in this run's manifest; tasks() may define more than an
# older checkpoint scored (e.g. probes added after the run).
run_tasks=[t for t in tasks() if t.task_id in manifest['decisions']]
expected={(run,task,v['tier']) for run in range(1,manifest['runs']+1)
          for task,d in manifest['decisions'].items() for v in d['policies'].values()}
completed=sum('score' in v for v in state.values())
lines=['# Policy screening results','',f'**Status: {completed}/{len(expected)} unique task/model/repetition outcomes scored.**',
       '', '[Protocol and limitations](policy_comparison.md). Prices include the unverified Gemma rate assumption. '
       'All policies share the same generation controls and matched answers. No production policy was changed.', '']
for group,policies in summary.items():
    if not any('n' in r for r in policies.values()): continue
    lines += ['## '+group.title(),'',
              '| Policy | Scored pairs | Quality (raw) | Delta raw (pts) | Exploratory 95% interval | Quality (fence-norm) | Delta norm (pts) | Estimated USD | Savings | Length finishes |',
              '|---|---:|---:|---:|---|---:|---:|---:|---:|---:|']
    for name,r in policies.items():
        if 'n' not in r: continue
        lo,hi=r['delta_ci95_points']
        lines.append(f"| {name} | {r['n']} ({r['missing']} missing) | {100*r['quality']:.2f}% | {r['quality_delta_points']:+.2f} | [{lo:+.2f}, {hi:+.2f}] | {100*r['quality_normalized']:.2f}% | {r['quality_delta_normalized_points']:+.2f} | ${r['estimated_usd']:.6f} | {r['savings_percent']:.1f}% | {r['length_finishes']} |")
    lines.append('')
lines += ['Raw = strict whole-response JSON (counts a code fence as a miss, i.e. instruction-following). '
          'Fence-norm = same scoring after removing a single surrounding code fence (capability). '
          'They differ only on json_exact suites.', '']
lines += ['## Category quality deltas','', 'Points relative to Kimi; negative means worse.','',
          '| Policy | '+ ' | '.join(sorted({d['suite'] for d in manifest['decisions'].values()}))+' |',
          '|---|'+'---:|'*len({d['suite'] for d in manifest['decisions'].values()})]
for name,r in summary['all'].items():
    if 'n' not in r: continue
    lines.append('| '+name+' | '+' | '.join(f"{r['suite_delta_points'].get(s,0):+.2f}" for s in sorted({d['suite'] for d in manifest['decisions'].values()}))+' |')
lines += ['', '## Category quality deltas (fence-normalized)','', 'Same as above after removing a single surrounding code fence; differs only on json_exact suites.','',
          '| Policy | '+ ' | '.join(sorted({d['suite'] for d in manifest['decisions'].values()}))+' |',
          '|---|'+'---:|'*len({d['suite'] for d in manifest['decisions'].values()})]
for name,r in summary['all'].items():
    if 'n' not in r: continue
    lines.append('| '+name+' | '+' | '.join(f"{r['suite_delta_normalized_points'].get(s,0):+.2f}" for s in sorted({d['suite'] for d in manifest['decisions'].values()}))+' |')
lines += ['', '## Routing mix', '', '| Policy | Model counts across task/repetitions |','|---|---|']
for name,r in summary['all'].items():
    lines.append('| '+name+' | '+str(r.get('model_counts',{}))+' |')
lines += ['', '## Objective full passes and repeatability', '',
          '| Policy | Full passes | Scored objective answers | Unstable task IDs |', '|---|---:|---:|---|']
for name in summary['all']:
    passed = total = 0
    unstable = []
    for task in run_tasks:
        if task.scoring_method == 'llm_judge': continue
        tier = manifest['decisions'][task.task_id]['policies'][name]['tier']
        scores = [state.get(f'{run}/{task.task_id}/{tier}', {}).get('score') for run in range(1, manifest['runs']+1)]
        known = [v for v in scores if v is not None]
        passed += sum(v == 1 for v in known)
        total += len(known)
        if len(known) == manifest['runs'] and len({v == 1 for v in known}) > 1:
            unstable.append(task.task_id)
    lines.append(f'| {name} | {passed} | {total} | {", ".join(unstable) or "none"} |')
lines += ['', '## Objective task failures and repeatability', '',
          'Full pass means score 1.0. A stable failure is still a failure. Open-ended rubric tasks are excluded from this table.', '',
          '| Policy | Task | Scores by repetition |', '|---|---|---|']
for name in summary['all']:
    for task in run_tasks:
        if task.scoring_method=='llm_judge': continue
        tier=manifest['decisions'][task.task_id]['policies'][name]['tier']
        scores=[state.get(f'{run}/{task.task_id}/{tier}',{}).get('score') for run in range(1,manifest['runs']+1)]
        if any(s!=1 for s in scores): lines.append(f'| {name} | {task.task_id} | {scores} |')
prior_errors = [e for v in state.values() for e in v.get('prior_errors', [])]
judge_attempts = [a for v in state.values() for a in v.get('judge_attempts', [])]
judge_usd = 0
from gatoway.reprice_eval import estimate_usd
for attempt in judge_attempts:
    if 'input_tokens' in attempt and 'output_tokens' in attempt:
        judge_usd += float(estimate_usd(dict(attempt, model_id=attempt['model']), manifest['prices']))
lines += ['', '## Infrastructure and latency', '',
          f'Initial unresolved attempts retained after recovery: {len(prior_errors)}. '
          f'Of these, {sum(e["usage_unknown"] for e in prior_errors)} have unknown token usage. '
          'Recovery uses a 600-second client timeout instead of 240 seconds, with the same prompt, '
          'temperature and 8,192-token budget. Savings exclude unreported usage from failed requests.', '',
          f'Judge attempts: {len(judge_attempts)}; failed attempts: {sum(a.get("status") != "ok" for a in judge_attempts)}. '
          f'Estimated judge cost with recorded usage: ${judge_usd:.6f}, excluded from policy answer costs.', '',
          '| Policy | Mean successful provider-call seconds |', '|---|---:|']
for name, r in summary['all'].items():
    if 'n' in r: lines.append(f'| {name} | {r["provider_seconds"]/r["n"]:.2f} |')
lines += ['', 'Durations exclude failed attempts, routing and grading. They are not end-to-end latency or retry-inclusive latency.', '']
lines += ['', '## Reproducibility', '', f"Source SHA256: `{manifest['source_hash']}`", '', f"Frozen bank SHA256: `{manifest['bank_hash']}`", '',
          'Raw responses, per-call tokens, judge attempts, routing evidence and the pricing snapshot are stored in the local checkpoint directory. '
          'Task-cluster bootstrap intervals are exploratory, not multiplicity-adjusted, and do not establish noninferiority. '
          'The fresh holdout contains only 16 structured/reasoning tasks. Shared Kimi answers make very conservative policies match the baseline by construction on fallback requests.', '']
args.output.write_text('\n'.join(lines))
(args.directory/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(f'{completed}/{len(expected)} scored; report: {args.output}')
