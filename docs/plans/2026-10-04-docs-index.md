# Docs Index & Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `docs/` one generated map — `docs/INDEX.md` — that lists every report with its status and (for derived reports) the exact command that regenerates it, and physically separate the two dead snapshots into `docs/archive/`.

**Architecture:** A single stdlib script, `scripts/build_docs_index.py`, holds an ordered `INDEX` dict (group → rows of filename/status/note/regen-command) and renders `docs/INDEX.md` from it. Status and grouping live in the script, **not** in the reports: six reports are overwritten in place by their generators, so any banner edited into a report is erased on the next run — the index must own that metadata. The script fails loudly (exit 1) when a `docs/*.md` file is unclassified, so a new report can never silently escape the map. We do **not** merge report bodies (their caveats are provenance and merging breaks the generators) and we do **not** build an OpenRouter renderer or a run-everything orchestrator (live inference + local-only artifacts make that out of scope).

**Tech Stack:** Python 3.13 stdlib only (`pathlib`, no third-party deps), pytest (`asyncio_mode = "auto"`). Run as `.venv/bin/python` / `.venv/bin/pytest`.

**Spec:** This plan is the spec — it implements the consolidation proposal agreed in conversation on 2026-10-04. No separate design doc.

## Global Constraints

- The virtualenv is at `.venv/`. Run everything as `.venv/bin/python` and `.venv/bin/pytest` — a bare `python`/`pytest` lacks the project install.
- Stdlib only for the new script. No new dependency (ponytail: a 60-line pathlib scan does not warrant one).
- The repo has no `Makefile`/`justfile`/pre-commit. The entrypoint convention is `.venv/bin/python -m gatoway.X` for package modules and `scripts/*.py` for meta tools (e.g. `scripts/report_policy_eval.py`). The index builder is a meta tool → `scripts/`, standalone, no `sys.path` hack needed for its own run.
- The full suite must stay green: run `.venv/bin/pytest -q` before starting and after each task.
- Most docs are untracked (`git status` shows `??`), so moves use plain `mv`, not `git mv`.
- Deliberate simplifications get a `ponytail:` comment naming the ceiling, matching the existing convention in `gatoway/providers.py`.
- `docs/INDEX.md` is generated and committed (so it is browsable on GitHub); it is excluded from the scan so it never classifies itself.

## Scope decisions (locked)

- **Archive only the two genuinely-superseded snapshots:** `judge_calibration_v1.md` (one inbound link, `docs/judge_calibration.md:81`) and `eval_report_pre_coding.md` (one live inbound link, `README.md:186`; a historical mention in `docs/plans/2026-09-24-coding-tasks.md:191` is a frozen plan record — leave it).
- **Do NOT archive `tasks.md`.** It is linked from `README.md` and `DESIGN.md` as the MVP breakdown; moving it forces edits to both for marginal gain. Relabel it `historical` in the index and point the index's Roadmap section at `docs/plans/` (the live roadmap).
- **Do NOT archive `eval_report.md`.** It is the live default output for `--suite legacy` and is pinned by `tests/test_eval_paths.py`; archiving it breaks that test or the file silently reappears.

## Review Focus

- **A report added to `docs/` later** → it must appear in `INDEX.md`, not silently vanish. Covered by `test_every_doc_is_classified` (Task 1).
- **A listed report moved or deleted** → the index must not point at a dead file. Covered by `test_classified_docs_all_exist` (Task 1).
- **`docs/archive/` missing when the script runs** → `glob` on a missing dir returns empty, so archive entries would be listed-but-absent; `test_classified_docs_all_exist` fails if the move was skipped (Task 1 creates the dir and moves the files).
- **Regenerating `eval_report_expanded.md`** → its hand-added monetary banner is overwritten. The index's Regeneration section states this in prose so no one is surprised (Task 1 render text).
- **`INDEX.md` classifying itself / churning** → excluded by name from the scan. Covered implicitly by `test_every_doc_is_classified` staying empty after a build writes `INDEX.md` (Task 2 runs the build, then the suite).

---

### Task 1: Archive the dead snapshots and build the index generator

**Files:**
- Create: `docs/archive/` (directory)
- Move: `docs/judge_calibration_v1.md` → `docs/archive/judge_calibration_v1.md`
- Move: `docs/eval_report_pre_coding.md` → `docs/archive/eval_report_pre_coding.md`
- Modify: `docs/judge_calibration.md:81` (link `judge_calibration_v1.md` → `archive/judge_calibration_v1.md`)
- Modify: `README.md:186` (link `docs/eval_report_pre_coding.md` → `docs/archive/eval_report_pre_coding.md`)
- Create: `scripts/build_docs_index.py`
- Test: `tests/test_docs_index.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `build_docs_index` module with `classified() -> set[str]`, `present() -> set[str]`, `unclassified() -> set[str]`, `render() -> str`, `main() -> int`. Filenames in `INDEX` are relative to `docs/` (archive entries carry the `archive/` prefix). Task 2 calls `main()` via the script's `__main__`.

- [ ] **Step 1: Create the archive dir and move the two snapshots**

```bash
cd /Users/azhou/Coding/gatoway
mkdir -p docs/archive
mv docs/judge_calibration_v1.md docs/archive/judge_calibration_v1.md
mv docs/eval_report_pre_coding.md docs/archive/eval_report_pre_coding.md
```

- [ ] **Step 2: Fix the two inbound links**

In `docs/judge_calibration.md`, line 81, change:

```
[judge_calibration_v1.md](judge_calibration_v1.md).
```
to:
```
[judge_calibration_v1.md](archive/judge_calibration_v1.md).
```

In `README.md`, line 186, change the link target `docs/eval_report_pre_coding.md` to `docs/archive/eval_report_pre_coding.md` (the `[docs/eval_report_pre_coding.md](...)` label text may stay or update to match; update it to `docs/archive/eval_report_pre_coding.md` for accuracy).

- [ ] **Step 3: Verify no stray links remain**

Run:
```bash
grep -rn "(judge_calibration_v1.md)\|(docs/eval_report_pre_coding.md)" README.md docs/*.md
```
Expected: no output (the only matches were the two just fixed). A match in `docs/plans/2026-09-24-coding-tasks.md` is a frozen plan record and is fine — the grep above does not scan `docs/plans/`.

- [ ] **Step 4: Write the failing test**

Create `tests/test_docs_index.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_docs_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_docs_index'`.

- [ ] **Step 6: Write the index generator**

Create `scripts/build_docs_index.py`:

```python
#!/usr/bin/env python3
"""Generate docs/INDEX.md: the single map of every report under docs/.

Status and grouping live here, not in the reports -- several reports are
overwritten in place by their generators, so any banner edited into them is
erased on the next run. This script owns that metadata and exits 1 when a
docs/*.md file is unclassified, so a new report can never silently escape the
index.

Run: .venv/bin/python scripts/build_docs_index.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"

# group -> rows of (filename_relative_to_docs, status, note, regen_cmd | None)
# status: current | generated | superseded | historical | stale
INDEX: dict[str, list[tuple[str, str, str, str | None]]] = {
    "Evaluation": [
        ("eval_report_expanded.md", "current",
         "32-task three-run router-vs-baseline eval; the live baseline.",
         ".venv/bin/python -m gatoway.eval --suite expanded"),
        ("eval_report.md", "current",
         "Legacy 16-task suite; still the default --suite legacy output.",
         ".venv/bin/python -m gatoway.eval"),
        ("evaluation_breadth.md", "current",
         "What the expanded 32-task suite covers and why it is a new baseline.",
         None),
        ("agentic_eval_report.md", "generated",
         "Agentic multi-step task eval.",
         ".venv/bin/python -m gatoway.agentic_eval"),
    ],
    "Routing policy": [
        ("policy_results.md", "current",
         "Seven-policy screening, 342/342 outcomes scored.",
         ".venv/bin/python scripts/report_policy_eval.py "
         "artifacts/policy_eval_20261004 --output docs/policy_results.md"),
        ("policy_comparison.md", "current",
         "Protocol and limitations for policy_results.md (hand-written).",
         None),
    ],
    "Cost": [
        ("openrouter_cost_comparison.md", "current",
         "OpenRouter USD counterfactual: 25.5% on 54/96 matched pairs. "
         "Hand-written prose around reprice_eval.py JSON; no renderer.",
         None),
    ],
    "Training bank": [
        ("bootstrap_report.md", "current",
         "288-observation measured bank bootstrap.", None),
        ("bank_density.md", "generated", "Bank coverage/density report.",
         ".venv/bin/python -m gatoway.bank_density"),
        ("nrp_characterization.md", "current",
         "Measured NRP model inventory.",
         ".venv/bin/python -m gatoway.characterize"),
    ],
    "Judge": [
        ("judge_calibration.md", "current",
         "Live rubric-json-v2 calibration (hand-written).", None),
        ("judge_reliability.md", "current",
         "rubric-json-v2 reliability probe.", None),
    ],
    "Roadmap & specs": [
        ("tasks.md", "historical",
         "Original July MVP breakdown. Live roadmap is docs/plans/.", None),
        ("spec.md", "current", "Architecture spec (v0.2, NRP).", None),
        ("agentic_benchmarks.md", "current",
         "Agentic benchmark task definitions.", None),
    ],
    "Archive": [
        ("archive/judge_calibration_v1.md", "superseded",
         "Original prompt-only judge calibration; see judge_calibration.md.",
         None),
        ("archive/eval_report_pre_coding.md", "historical",
         "Eval snapshot before coding tasks were added.", None),
    ],
}


def classified() -> set[str]:
    return {row[0] for rows in INDEX.values() for row in rows}


def present() -> set[str]:
    top = {p.name for p in DOCS_DIR.glob("*.md") if p.name != "INDEX.md"}
    arch = {f"archive/{p.name}" for p in (DOCS_DIR / "archive").glob("*.md")}
    return top | arch


def unclassified() -> set[str]:
    return present() - classified()


def render() -> str:
    lines = [
        "# Docs index", "",
        "Generated by `scripts/build_docs_index.py` -- do not edit by hand.",
        "Status and grouping live here because several reports are overwritten "
        "in place by their generators.", "",
        "Status: **current** | **generated** (regenerable, see command) | "
        "**superseded** | **historical** | **stale**.", "",
    ]
    for group, rows in INDEX.items():
        lines += [f"## {group}", "", "| Report | Status | Notes |",
                  "|---|---|---|"]
        for name, status, note, _ in rows:
            lines.append(f"| [{name}]({name}) | {status} | {note} |")
        lines.append("")
    regen = [(n, c) for rows in INDEX.values() for n, _, _, c in rows if c]
    lines += [
        "## Regeneration", "",
        "Derived reports and the exact command that rewrites each. "
        "Regenerating needs the live eval run or a local `artifacts/` "
        "checkpoint; it is not cheap. Note: regenerating "
        "`eval_report_expanded.md` overwrites its hand-added monetary banner.",
        "", "| Report | Command |", "|---|---|",
    ]
    for name, cmd in regen:
        lines.append(f"| {name} | `{cmd}` |")
    lines += [
        "", "## Roadmap", "",
        "The live roadmap is the dated plans in [docs/plans/](plans/) and the "
        "specs in [docs/specs/](specs/).", "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    missing = unclassified()
    if missing:
        print("Unclassified docs (add to INDEX in build_docs_index.py):",
              file=sys.stderr)
        for name in sorted(missing):
            print(f"  {name}", file=sys.stderr)
        return 1
    (DOCS_DIR / "INDEX.md").write_text(render())
    print(f"Wrote {DOCS_DIR / 'INDEX.md'} ({len(classified())} reports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_docs_index.py -v`
Expected: PASS (3 passed). If `test_every_doc_is_classified` fails, the failure message names any `docs/*.md` missing from `INDEX` — add it to the right group. If `test_classified_docs_all_exist` fails, a move in Step 1 was skipped or a filename in `INDEX` is misspelled.

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass (prior green count + 3 new).

- [ ] **Step 9: Commit**

```bash
git add scripts/build_docs_index.py tests/test_docs_index.py \
  docs/archive/judge_calibration_v1.md docs/archive/eval_report_pre_coding.md \
  docs/judge_calibration.md README.md
git rm --cached --ignore-unmatch docs/judge_calibration_v1.md docs/eval_report_pre_coding.md 2>/dev/null || true
git commit -m "Add docs index generator; archive superseded eval/judge snapshots"
```

---

### Task 2: Generate `docs/INDEX.md` and point README at it

**Files:**
- Create: `docs/INDEX.md` (generated output, committed)
- Modify: `README.md` (one line linking to `docs/INDEX.md` near the top of the docs/results section)

**Interfaces:**
- Consumes: `scripts/build_docs_index.py` from Task 1 (`main()`).
- Produces: `docs/INDEX.md` on disk; a README pointer. Nothing later depends on these.

- [ ] **Step 1: Generate the index**

Run: `.venv/bin/python scripts/build_docs_index.py`
Expected: prints `Wrote .../docs/INDEX.md (N reports)` and exits 0. If it exits 1, it lists an unclassified doc — add it to `INDEX` and rerun.

- [ ] **Step 2: Eyeball the output**

Run: `.venv/bin/python -c "print(open('docs/INDEX.md').read())"` (or open it). Confirm every group is present, the archive links read `archive/...`, and the Regeneration table lists the generated reports with runnable commands.

- [ ] **Step 3: Add the README pointer**

In `README.md`, near the top of the results/docs section (around line 17, "that produces the cost/effectiveness report below"), add one line:

```markdown
All reports are indexed in [docs/INDEX.md](docs/INDEX.md), which lists each one's status and how to regenerate it.
```

- [ ] **Step 4: Confirm the suite still passes**

Run: `.venv/bin/pytest -q`
Expected: all pass — writing `INDEX.md` must not make `test_every_doc_is_classified` fail (INDEX.md is excluded from the scan).

- [ ] **Step 5: Commit**

```bash
git add docs/INDEX.md README.md
git commit -m "Generate docs/INDEX.md and link it from README"
```

---

## Out of scope (recorded so it is not re-litigated)

- **Merging report bodies.** Each report's caveats are provenance; six are generator-owned. Merging loses the caveats and breaks regeneration.
- **An OpenRouter renderer.** `openrouter_cost_comparison.md` is hand-written prose around `reprice_eval.py` JSON. One doc does not warrant a renderer (YAGNI).
- **A run-everything orchestrator.** Regenerating the derived reports needs live inference and local-only `artifacts/` checkpoints; a one-button rerun would be fragile and expensive. The index documents each regen command instead.
- **A `Makefile`/pre-commit hook.** The repo has neither; two scripts do not justify introducing a build system. Run the generator by hand (or wire a hook later if the index drifts in practice).
