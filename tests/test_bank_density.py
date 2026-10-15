import pytest

import gatoway.bank_density as module
from gatoway.providers import MODEL_LADDER


async def test_density_distinguishes_observation_count_from_effectiveness(monkeypatch):
    rows = []
    for rung, score in zip(MODEL_LADDER[:2], [0.0, 1.0]):
        for index in range(2):
            rows.append(dict(routing_id=index, model_id=rung.primary,
                             calculated_effectiveness=score, calculated_difficulty=.5,
                             similarity=.8))
    rows.append(dict(routing_id=99, model_id=MODEL_LADDER[2].primary,
                     calculated_effectiveness=1.0, calculated_difficulty=.5, similarity=.2))
    monkeypatch.setattr(module, "embed", lambda text: [1.0])
    async def fetch(vector, pool):
        return rows
    monkeypatch.setattr(module, "fetch_neighbors", fetch)
    results = await module.measure(object())
    for row in results:
        assert row["rungs_with_evidence"] == [r.name for r in MODEL_LADDER[:2]]
        assert row["rungs_clearing_bar"] == [MODEL_LADDER[1].name]
        assert row["selected_rung"] == MODEL_LADDER[1].name
        assert not row["low_confidence"]
    assert results[8]["threshold"] == results[0]["threshold"]
