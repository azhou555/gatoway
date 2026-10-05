"""Held-out objective tasks. No provider, code execution, or train-bank writes."""

import json
import math
import re
from pathlib import Path

# A whole response that is a single fenced block, optionally tagged ```json.
_FENCE = re.compile(r"^```[^\n`]*\n(.*)\n```$", re.DOTALL)

TASK_PATH = Path(__file__).resolve().parent.parent / "benchmarks/breadth/tasks.json"


def load_cases():
    return json.loads(TASK_PATH.read_text())


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _equal(actual, expected):
    # JSON numbers may be represented with or without a decimal point, but
    # Python's True == 1 must never let a boolean pass as a numeric answer.
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isfinite(actual) and actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _equal(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(map(lambda pair: _equal(*pair), zip(actual, expected)))
    return actual == expected


def score_json(response: str, expected) -> float:
    """Strict whole-response parsing; compare values, types, keys and ordering."""
    def invalid_constant(value):
        raise ValueError(f"non-JSON constant: {value}")
    try:
        actual = json.loads(response, object_pairs_hook=_unique_keys,
                            parse_constant=invalid_constant)
        return float(_equal(actual, expected))
    except (ValueError, TypeError, RecursionError, OverflowError):
        return 0.0


def strip_json_fence(response: str) -> str:
    """Return the inner text if the whole response is one fenced block, else as-is.

    Models often wrap JSON in a ```json ... ``` block. That breaks strict
    whole-response parsing but is not a correctness error, so scoring can see
    through it while the raw score still records the instruction-following miss.
    """
    match = _FENCE.match(response.strip())
    return match.group(1).strip() if match else response


def score_json_normalized(response: str, expected) -> float:
    """Fence-tolerant score: the strict score, or the strict score of the
    response with a single surrounding code fence removed. Never below
    ``score_json``; use alongside it to separate format from capability."""
    raw = score_json(response, expected)
    if raw == 1.0:
        return raw
    return score_json(strip_json_fence(response), expected)
