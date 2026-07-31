"""Local embedding function backed by sentence-transformers.

Model: all-MiniLM-L6-v2 (384 dims), matches VECTOR(384) columns in schema.sql.
Loaded lazily on first call so importing this module (e.g. in tests that mock
`embed`) doesn't pay the model-load cost.
"""

from __future__ import annotations

MODEL_NAME = "all-MiniLM-L6-v2"

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(text: str) -> list[float]:
    """Embed `text` into a 384-dim vector using all-MiniLM-L6-v2."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=False)
    return vector.tolist()
