"""Experimental policies; production routing remains unchanged.

Evidence must come only from the frozen training bank. Prompt IDs identify paired
outcomes, never evaluation labels. Thresholds are fixed before live evaluation.
"""
from gatoway.providers import MODEL_LADDER, RUNG_BY_NAME
from gatoway.router import decide, CONFIDENCE_FLOOR
from gatoway.reprice_eval import estimate_usd

POLICIES = ('current', 'frontier_fallback', 'paired_quality', 'price_order',
            'strict_evidence', 'paired_price', 'always_kimi')


def select(policy, neighbors, input_tokens, threshold, prices):
    if policy not in POLICIES:
        raise ValueError(policy)
    capable = [r for r in MODEL_LADDER if r.context_tokens >= input_tokens + 8192]
    if not capable or 'kimi' not in {r.name for r in capable}:
        raise ValueError('Experiment requires inputs that fit the Kimi control')
    old = decide(neighbors, [], input_tokens + 8192, threshold)
    if policy == 'current':
        return {'tier': old.tier, 'reason': 'current', 'evidence_count': old.observation_count}
    if policy == 'always_kimi' or (policy == 'frontier_fallback' and old.low_confidence):
        return {'tier': 'kimi', 'reason': 'frontier_fallback', 'evidence_count': 0}
    if policy == 'frontier_fallback':
        return {'tier': old.tier, 'reason': 'current_evidence', 'evidence_count': old.observation_count}
    floor = .4 if policy in ('strict_evidence', 'paired_price') else CONFIDENCE_FLOOR
    bar = .7 + (threshold - .5) * .5
    eligible = []
    baseline = {n['prompt_id']: n['calculated_effectiveness'] for n in neighbors
                if n['model_id'] == 'openai/kimi' and n['similarity'] >= floor}
    for rung in capable:
        observations = [n for n in neighbors if n['model_id'] == rung.primary
                        and n['similarity'] >= floor and n['calculated_effectiveness'] is not None]
        minimum = 2 if policy == 'price_order' else 3
        if policy in ('paired_quality', 'paired_price'):
            observations = [n for n in observations if n['prompt_id'] in baseline
                            and baseline[n['prompt_id']] is not None]
        if len(observations) < minimum:
            continue
        scores = [n['calculated_effectiveness'] for n in observations]
        if sum(scores) / len(scores) < bar:
            continue
        if policy == 'strict_evidence' and min(scores) < .95:
            continue
        if policy in ('paired_quality', 'paired_price'):
            differences = [n['calculated_effectiveness'] - baseline[n['prompt_id']] for n in observations]
            if sum(differences) < -1e-9:
                continue
            if policy == 'paired_price' and min(differences) < -1e-9:
                continue
        eligible.append((rung.name, len(observations)))
    if policy in ('price_order', 'paired_price'):
        def price(item):
            return estimate_usd({'model_id': RUNG_BY_NAME[item[0]].primary,
                                 'input_tokens': input_tokens, 'output_tokens': 1024}, prices)
        eligible = [item for item in eligible if price(item) is not None]
        eligible.sort(key=price)
    if eligible:
        tier, count = eligible[0]
        return {'tier': tier, 'reason': policy, 'evidence_count': count}
    return {'tier': 'gpt-oss' if policy == 'price_order' else 'kimi',
            'reason': 'insufficient_evidence', 'evidence_count': 0}
