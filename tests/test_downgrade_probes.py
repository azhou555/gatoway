"""Downgrade-safety probe set: structure and no-leakage guards.

Routing (that each probe reaches its cheap rung under strict_evidence) is a
live check against the bank, exercised by policy_eval --prepare-only, not here.
"""
import json
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from gatoway.bank_corpus import TRAIN_PROMPTS, assert_no_eval_overlap

PROBES = json.loads(Path("benchmarks/breadth/downgrade_probes.json").read_text())


def test_probe_set_shape():
    assert len(PROBES) == 30
    assert {p["suite"] for p in PROBES} == {"probe_glm5", "probe_gemma"}
    for p in PROBES:
        assert p["prompt"].strip()
        assert set(p["answer"]) == {"result"}  # single-key answer avoids JSON key-ordering
        assert "only JSON" in p["prompt"]  # json_exact needs a JSON-only response


def test_task_ids_unique():
    ids = [p["task_id"] for p in PROBES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("prompt", [p["prompt"] for p in PROBES])
def test_probe_does_not_overlap_eval_tasks(prompt):
    # Reuses the eval-overlap guard (normalized exact + similarity >= 0.85).
    assert_no_eval_overlap([prompt])


@pytest.mark.parametrize("prompt", [p["prompt"] for p in PROBES])
def test_probe_does_not_duplicate_a_training_prompt(prompt):
    normalized = " ".join(prompt.casefold().split())
    for train in TRAIN_PROMPTS:
        ratio = SequenceMatcher(None, normalized,
                                " ".join(train.prompt.casefold().split())).ratio()
        assert ratio < 0.85, f"{prompt!r} duplicates train {train.prompt_id} (ratio={ratio:.3f})"
