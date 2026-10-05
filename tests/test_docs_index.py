"""docs/INDEX.md covers every report under docs/ and renders deterministically.

Guards two ways: no report under docs/ escapes the index (a new report would
otherwise never appear on the map), and no index entry points at a moved or
deleted file. The index owns status/grouping because several reports are
overwritten in place by their generators -- see scripts/build_docs_index.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_docs_index as idx


def test_every_doc_is_classified():
    assert idx.unclassified() == set(), (
        "docs not in INDEX; add them to build_docs_index.INDEX")


def test_classified_docs_all_exist():
    assert idx.classified() <= idx.present(), (
        "INDEX lists a file that is not present under docs/")


def test_render_is_deterministic():
    assert idx.render() == idx.render()
