"""The eval report is written under docs/, not the repo root.

Guards the docs consolidation from docs/specs/2026-09-04-wide-ladder-design.md
§3 -- a stray REPORT_PATH would silently recreate eval_report.md at the root
on the next eval run.
"""

from pathlib import Path

from gatoway.eval import REPORT_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_report_path_is_under_docs():
    assert REPORT_PATH == REPO_ROOT / "docs" / "eval_report.md"


def test_consolidated_docs_exist_and_root_copies_do_not():
    for name in ("spec.md", "tasks.md"):
        assert (REPO_ROOT / "docs" / name).is_file(), f"docs/{name} missing"
    for stale in ("SPEC.md", "TASKS.md", "eval_report.md"):
        assert not (REPO_ROOT / stale).exists(), f"{stale} should have moved under docs/"
