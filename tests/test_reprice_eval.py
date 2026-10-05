from decimal import Decimal

import pytest

from gatoway.reprice_eval import compare, estimate_usd


SNAPSHOT = {'retrieved_at': '2026-10-04', 'models': {
    'priced': {'openrouter_id': 'example/model',
               'pricing': {'prompt': '0.000001', 'completion': '0.000003'}}}}


def response(model='priced', input_tokens=100, output_tokens=200):
    return dict(model_id=model, input_tokens=input_tokens, output_tokens=output_tokens,
                cost_cents=999999)


def test_separate_input_output_rates_ignore_legacy_proxy():
    assert estimate_usd(response(), SNAPSHOT) == Decimal('0.0007')


def test_unknown_is_not_free():
    assert estimate_usd(response('unknown'), SNAPSHOT) is None
    result = compare([{'signature': 'a', 'responses': {
        'one/router/small': response('unknown'),
        'one/baseline/large': response(),
        'two/router/small': response(output_tokens=100),
        'two/baseline/large': response(),
    }}], SNAPSHOT)
    assert result['full_reduction_percent'] is None
    assert result['matched_pairs'] == 1
    assert result['matched_pair_usd']['baseline'] == '0.000700'
    assert result['matched_pair_reduction_percent'] == pytest.approx(100 * 3 / 7)


@pytest.mark.parametrize('tokens', [-1, 1.5, True])
def test_invalid_usage(tokens):
    with pytest.raises(ValueError):
        estimate_usd(response(input_tokens=tokens), SNAPSHOT)


def test_missing_pair_rejected():
    with pytest.raises(ValueError, match='Unpaired'):
        compare([{'signature': 'a', 'responses': {'one/router/small': response()}}], SNAPSHOT)


def test_complete_comparison():
    result = compare([{'signature': 'a', 'responses': {
        'one/router/small': response(), 'one/baseline/large': response(),
    }}], SNAPSHOT)
    assert result['full_comparison_available']
    assert result['full_reduction_percent'] == 0
