"""Offline, coverage-aware OpenRouter list-price estimates for saved live answers.

No inference or network calls. Historical cost_cents fields are never consumed.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def estimate_usd(response, snapshot):
    entry = snapshot['models'].get(response['model_id'])
    if entry is None or not entry.get('pricing'):
        return None
    total = Decimal(0)
    for usage, rate in [('input_tokens', 'prompt'), ('output_tokens', 'completion')]:
        tokens = response[usage]
        price = Decimal(entry['pricing'][rate])
        if type(tokens) is not int or tokens < 0 or not price.is_finite() or price < 0:
            raise ValueError('Invalid token count or price')
        total += tokens * price
    return total


def compare(checkpoints, snapshot):
    sums = {'router': Decimal(0), 'baseline': Decimal(0)}
    paired = {'router': Decimal(0), 'baseline': Decimal(0)}
    counts = Counter()
    missing = Counter()
    rows = []
    pairs = 0
    signatures = set()
    for run, checkpoint in enumerate(checkpoints, 1):
        signatures.add(checkpoint['signature'])
        tasks = {}
        for key, response in checkpoint['responses'].items():
            task, side, tier = key.split('/')
            if side not in sums:
                raise ValueError(f'Unknown side: {side}')
            if side in tasks.setdefault(task, {}):
                raise ValueError(f'Duplicate answer: {task}/{side}')
            cost = estimate_usd(response, snapshot)
            tasks[task][side] = cost
            counts[side] += 1
            if cost is None:
                missing[response['model_id']] += 1
            else:
                sums[side] += cost
                counts[side + '_priced'] += 1
            rows.append({'run': run, 'key': key,
                         'model_id': response['model_id'],
                         'estimated_usd': str(cost) if cost is not None else None})
        for task, sides in tasks.items():
            if set(sides) != set(sums):
                raise ValueError(f'Unpaired task: {task}')
            if all(value is not None for value in sides.values()):
                pairs += 1
                for side, value in sides.items():
                    paired[side] += value
    if len(signatures) != 1:
        raise ValueError('Checkpoints must share one evaluation signature')
    complete = all(counts[s] == counts[s + '_priced'] for s in sums)
    reduction = lambda a, b: float(100 * (1 - a / b)) if b else None
    return {
        'basis': snapshot.get('basis', 'openrouter_uncached_text_list_price_estimate'),
        'retrieved_at': snapshot['retrieved_at'],
        'evaluation_signature': next(iter(signatures)),
        'coverage': dict(counts), 'unpriced_answers': dict(missing),
        'full_comparison_available': complete,
        'full_reduction_percent': reduction(sums['router'], sums['baseline']) if complete else None,
        'known_subtotals_usd': {s: str(v) for s, v in sums.items()},
        'matched_pairs': pairs,
        'matched_pair_usd': {s: str(v) for s, v in paired.items()},
        'matched_pair_reduction_percent': reduction(paired['router'], paired['baseline']),
        'answers': rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--checkpoints', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(set(p.resolve() for p in args.checkpoints)) != len(args.checkpoints):
        parser.error('Duplicate checkpoint paths')
    snapshot_bytes = args.snapshot.read_bytes()
    checkpoints = [json.loads(p.read_text()) for p in args.checkpoints]
    report = compare(checkpoints, json.loads(snapshot_bytes))
    report['snapshot_sha256'] = hashlib.sha256(snapshot_bytes).hexdigest()
    report['checkpoint_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in args.checkpoints}
    with args.output.open('x') as out:
        json.dump(report, out, indent=2)
        out.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'answers'}, indent=2))


if __name__ == '__main__':
    main()
