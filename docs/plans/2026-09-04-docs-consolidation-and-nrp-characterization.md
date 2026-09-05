# Docs Consolidation & NRP Characterization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all project docs under `docs/`, bring the architecture spec in line with the NRP migration (v0.2), and produce a measured characterization of NRP's model inventory that the wide ladder will be built from.

**Architecture:** Steps 1 and 2 of `docs/specs/2026-09-04-wide-ladder-design.md`. Tasks 1–2 are documentation and path plumbing with no behavior change. Task 3 adds `gatoway/characterize.py`, a standalone probe that repeatedly calls every NRP model and reports served-id deduplication, availability, latency, and context window. Task 4 runs it and folds the findings back into the design doc's rung table.

**Tech Stack:** Python 3.13, pytest (`asyncio_mode = "auto"`), litellm against NRP's OpenAI-compatible endpoint, `python-dotenv`.

**Spec:** `docs/specs/2026-09-04-wide-ladder-design.md`

## Global Constraints

- The virtualenv is at `.venv/`. Run everything as `.venv/bin/python` and `.venv/bin/pytest` — a bare `python`/`pytest` will not have the project installed.
- `NRP_API_KEY` must be set in `.env` (already present). `gatoway/providers.py` calls `load_dotenv()` at import.
- NRP API base: `https://ellm.nrp-nautilus.io/v1`. Auth is `Authorization: Bearer <key>`. litellm model strings use the `openai/` prefix with an explicit `api_base`.
- The full suite must stay green: `.venv/bin/pytest -q` → 48 passed before this plan starts.
- Deliberate simplifications get a `ponytail:` comment naming the ceiling and the upgrade path, matching the existing convention in `gatoway/providers.py` and `schema.sql`.
- Docstrings referencing `SPEC.md §N` are **left alone** — they name a section, not a path, and stay accurate after the move. Only true path references change.
- **Do not add an ANN index to `decision_history`.** `schema.sql` documents why it was removed; the spec is what is wrong, not the code.

---

### Task 1: Move docs under `docs/` and fix path references

**Files:**
- Move: `SPEC.md` → `docs/spec.md`
- Move: `TASKS.md` → `docs/tasks.md`
- Move: `eval_report.md` → `docs/eval_report.md`
- Modify: `gatoway/eval.py:48` (`REPORT_PATH`)
- Modify: `README.md:8`, `README.md:170`
- Test: `tests/test_eval_paths.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `gatoway.eval.REPORT_PATH` now resolves to `<repo>/docs/eval_report.md`. Task 2 edits `docs/spec.md` at its new path.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_paths.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_eval_paths.py -v`

Expected: FAIL. `test_report_path_is_under_docs` fails because `REPORT_PATH` still points at the repo root; `test_consolidated_docs_exist_and_root_copies_do_not` fails on missing `docs/spec.md`.

- [ ] **Step 3: Move the files with git**

Use `git mv` so history follows the files:

```bash
git mv SPEC.md docs/spec.md
git mv TASKS.md docs/tasks.md
git mv eval_report.md docs/eval_report.md
```

- [ ] **Step 4: Update `REPORT_PATH`**

In `gatoway/eval.py`, replace line 48:

```python
REPORT_PATH = Path(__file__).resolve().parent.parent / "eval_report.md"
```

with:

```python
REPORT_PATH = Path(__file__).resolve().parent.parent / "docs" / "eval_report.md"
```

- [ ] **Step 5: Update the two README path references**

`README.md` line 8, replace:

```markdown
Full architecture: `SPEC.md`. Subtask breakdown: `TASKS.md`.
```

with:

```markdown
Full architecture: `docs/spec.md`. Subtask breakdown: `docs/tasks.md`.
Design docs and implementation plans live in `docs/specs/` and `docs/plans/`.
```

`README.md` line 170, replace:

```markdown
- `gatoway/eval.py` — benchmark harness, produces `eval_report.md`.
```

with:

```markdown
- `gatoway/eval.py` — benchmark harness, produces `docs/eval_report.md`.
```

Leave every other `SPEC.md §N` mention in README and TASKS alone — those name sections, per Global Constraints.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_eval_paths.py -v`
Expected: PASS, 2 tests.

Then the full suite: `.venv/bin/pytest -q`
Expected: PASS, 50 passed.

- [ ] **Step 7: Verify no dangling doc references remain**

Run:

```bash
grep -rn "eval_report\.md" --include='*.py' --include='*.md' . | grep -v '^\./\.venv' | grep -v 'docs/eval_report\.md'
```

Expected: only lines where `eval_report.md` appears as prose inside `docs/` or `README.md` narrative (e.g. "spelled out in full in `eval_report.md`"). Update any of those to `docs/eval_report.md` for accuracy. No `.py` file should appear in the output.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Move docs under docs/, repoint eval report path

Consolidates SPEC.md, TASKS.md and eval_report.md under docs/ alongside
docs/specs/ and docs/plans/. Docstring references to 'SPEC.md SS N' are
left alone: they name a section, not a path.

Claude-Session: https://claude.ai/code/session_013J4bQFhu3pRp5TSwokHm5n"
```

---

### Task 2: Bring the spec to v0.2

**Files:**
- Modify: `docs/spec.md` (sections 2, 3, 4, 5, 10)

**Interfaces:**
- Consumes: `docs/spec.md` at its post-Task-1 path.
- Produces: a spec that matches the implementation. Task 4 and later plans cite `docs/spec.md §N`; section numbers do not change.

This task is prose only — no code, no tests. Its deliverable is a spec a reader can trust. Section numbering stays stable so the ~60 docstring references remain valid.

- [ ] **Step 1: Update the version heading**

Change the title line from:

```markdown
# Cost-Aware LLM Gateway — Architecture Spec (v0.1)
```

to:

```markdown
# Cost-Aware LLM Gateway — Architecture Spec (v0.2)

> v0.2 (2026-09-04) moved every provider tier onto NRP-hosted open-weights
> models and reconciled this document with the implementation. The wide
> model ladder that replaces the three-tier scheme is designed in
> `docs/specs/2026-09-04-wide-ladder-design.md`; this spec describes the
> system as built.
```

- [ ] **Step 2: Fix the §2 architecture diagram**

In the mermaid block, replace the provider node:

```
    CB -->|selected provider call| PROV[Provider Adapters<br/>Anthropic / OpenAI / OpenRouter / Ollama]
```

with:

```
    CB -->|selected provider call| PROV[Provider Adapter<br/>NRP OpenAI-compatible endpoint]
```

- [ ] **Step 3: Fix the §3 component table**

Replace the Provider Adapters row's Responsibility cell:

```
Thin wrapper per provider (Anthropic, OpenAI, OpenRouter, Ollama for local cheap tier)
```

with:

```
Thin litellm wrapper over NRP's single OpenAI-compatible endpoint; tier -> model list + parameter-count cost proxy
```

- [ ] **Step 4: Fix the §4 schema block**

Two changes in the `decision_history` SQL:

Change all three `VECTOR(1536)` declarations to `VECTOR(384)`, and delete this line entirely:

```sql
CREATE INDEX ON decision_history USING ivfflat (input_embedding vector_cosine_ops);
```

Replace it with:

```sql
-- No ANN index. ivfflat's default `lists` is oversized for a bank this
-- small, so probes=1 misses the true nearest neighbor -- see schema.sql
-- for the EXPLAIN ANALYZE that showed it. Exact seq scan until a scan is
-- a measured bottleneck.
```

Then update the `VECTOR(n)` note below the block to say the embedding model is `all-MiniLM-L6-v2` at 384 dimensions, chosen so the demo runs without an embedding API key.

- [ ] **Step 5: Fix the two "Sonnet" references**

In §4's notes, replace:

```markdown
  neighbor similarity is below a set floor, route to Sonnet and mark the row
```

with:

```markdown
  neighbor similarity is below a set floor, route to the fallback rung and
  mark the row
```

In §5's mermaid state diagram, replace:

```
    ClassifierFailed --> UseMediumTier: default to Sonnet, single request, no breaker
```

with:

```
    ClassifierFailed --> UseFallbackRung: single request, no breaker
```

and rename the following `UseMediumTier --> CallProvider` transition to `UseFallbackRung --> CallProvider`.

- [ ] **Step 6: Close the two resolved §10 open questions**

Replace these two lines:

```markdown
- [ ] Pick embedding model (dimension affects `VECTOR(n)` above — placeholder is 1536)
- [ ] Define similarity-confidence floor for the "no good match" fallback
```

with:

```markdown
- [x] Pick embedding model — `all-MiniLM-L6-v2`, 384 dims, local (no API key)
- [x] Define similarity-confidence floor — 0.3 (`router.CONFIDENCE_FLOOR`)
```

- [ ] **Step 7: Verify no stale provider references survive**

Run:

```bash
grep -niE 'anthropic|sonnet|opus|haiku|openrouter|1536|ivfflat' docs/spec.md
```

Expected: no matches, except any line inside the new note that mentions ivfflat as the thing deliberately *not* used. Every other hit is a section this task missed — go back and fix it.

- [ ] **Step 8: Commit**

```bash
git add docs/spec.md
git commit -m "Spec v0.2: reconcile architecture spec with NRP implementation

The spec still described Anthropic/OpenAI/OpenRouter tiers, VECTOR(1536),
and an ivfflat index that schema.sql deliberately dropped with a written
rationale. Where the two disagreed the implementation was right. Also
closes the two resolved open questions in SS 10.

Claude-Session: https://claude.ai/code/session_013J4bQFhu3pRp5TSwokHm5n"
```

---

### Task 3: NRP characterization probe

**Files:**
- Create: `gatoway/characterize.py`
- Test: `tests/test_characterize.py` (create)

**Interfaces:**
- Consumes: `gatoway.providers.NRP_API_BASE`.
- Produces:
  - `ProbeResult` dataclass: `name: str`, `served_id: str | None`, `latency_ms: float | None`, `error: str | None`
  - `ModelSummary` dataclass: `name: str`, `served_id: str | None`, `rounds_ok: int`, `rounds_total: int`, `median_latency_ms: float | None`
  - `summarize(rounds: list[list[ProbeResult]]) -> list[ModelSummary]`
  - `group_by_served_id(summaries: list[ModelSummary]) -> dict[str, list[str]]`
  - `async probe_model(name: str, api_key: str) -> ProbeResult`
  - `async run(rounds: int) -> list[list[ProbeResult]]`

**Why this is not `bench_latency.py`:** that benchmark replaces the provider call with an instant stand-in on purpose, because spec §9 excludes provider latency from the gateway's overhead budget. It measures the opposite of what the ladder needs.

The network probe is split from the analysis so the analysis is unit-testable without hitting NRP.

**Verified before this plan was written:** litellm's `response.model` returns
the *served* id, not the requested name — `openai/gemma-small` and
`openai/gemma4-12b` both come back as `google/gemma-4-12B-it-qat-w4a16-ct`,
while `openai/qwen3-small` returns `Qwen/Qwen3.8-27B`. The deduplication in
`group_by_served_id()` depends on this and it holds. `httpx` is already
importable in `.venv`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_characterize.py`:

```python
"""Pure analysis half of the NRP characterization probe.

The network half (probe_model/run) is not unit-tested -- it is a thin
litellm call. Everything that can get the answer *wrong* lives in
summarize()/group_by_served_id(), so that is what is tested.
"""

from gatoway.characterize import (
    ModelSummary,
    ProbeResult,
    group_by_served_id,
    summarize,
)


def ok(name, served_id, latency_ms):
    return ProbeResult(name=name, served_id=served_id, latency_ms=latency_ms, error=None)


def fail(name, error="boom"):
    return ProbeResult(name=name, served_id=None, latency_ms=None, error=error)


def test_summarize_counts_availability_across_rounds():
    rounds = [
        [ok("a", "vendor/A", 100.0)],
        [fail("a")],
        [ok("a", "vendor/A", 200.0)],
    ]
    (summary,) = summarize(rounds)
    assert summary.name == "a"
    assert summary.rounds_ok == 2
    assert summary.rounds_total == 3


def test_summarize_uses_median_latency_of_successful_rounds_only():
    rounds = [
        [ok("a", "vendor/A", 100.0)],
        [fail("a")],
        [ok("a", "vendor/A", 300.0)],
        [ok("a", "vendor/A", 200.0)],
    ]
    (summary,) = summarize(rounds)
    # median of 100/300/200 is 200 -- the failed round must not count as 0
    assert summary.median_latency_ms == 200.0


def test_summarize_reports_a_never_working_model_with_no_latency():
    (summary,) = summarize([[fail("dead")], [fail("dead")]])
    assert summary.rounds_ok == 0
    assert summary.median_latency_ms is None
    assert summary.served_id is None


def test_group_by_served_id_collapses_aliases():
    summaries = [
        ModelSummary("gemma-small", "google/gemma-4-12B", 1, 1, 10.0),
        ModelSummary("gemma4-small", "google/gemma-4-12B", 1, 1, 12.0),
        ModelSummary("qwen3-small", "Qwen/Qwen3.8-27B", 1, 1, 20.0),
    ]
    groups = group_by_served_id(summaries)
    assert groups["google/gemma-4-12B"] == ["gemma-small", "gemma4-small"]
    assert groups["Qwen/Qwen3.8-27B"] == ["qwen3-small"]


def test_group_by_served_id_excludes_models_that_never_responded():
    summaries = [
        ModelSummary("alive", "vendor/A", 1, 1, 10.0),
        ModelSummary("dead", None, 0, 2, None),
    ]
    groups = group_by_served_id(summaries)
    assert list(groups) == ["vendor/A"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_characterize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gatoway.characterize'`.

- [ ] **Step 3: Write the implementation**

Create `gatoway/characterize.py`:

```python
"""NRP model characterization probe.

Produces the measured inputs the wide model ladder is built from, per
docs/specs/2026-09-04-wide-ladder-design.md SS 8.1:

  - served model id, so aliases collapse (three NRP names resolve to one
    served gemma-4-12B; a ladder built off /v1/models without deduplicating
    would have phantom rungs)
  - availability across repeated rounds (two models failed a single probe
    during the migration -- persistent or transient?)
  - median latency per model, the observed second signal against the
    published parameter count, which is unreliable for MoE models where
    total and active params disagree

This is deliberately NOT gatoway/bench_latency.py: that benchmark stubs the
provider call out to an instant stand-in, because spec SS 9 excludes provider
latency from the gateway's overhead budget. It measures the opposite thing.

Usage:
    python -m gatoway.characterize [ROUNDS]   # default 3
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time
from dataclasses import dataclass

import httpx
import litellm

from gatoway.providers import NRP_API_BASE

# Short, cheap, and answerable by every model regardless of size, so a slow
# result means a slow model rather than a hard question.
PROBE_PROMPT = "Reply with the single word: ok"
PROBE_MAX_TOKENS = 5

# ponytail: a model that has not answered in 60s is unusable for routing
# either way, so timing out is the same answer as failing. Raise this only
# if a rung turns out to be genuinely slow but worth keeping.
PROBE_TIMEOUT_S = 60.0

# Not a chat model -- it has no chat/completions endpoint to probe.
SKIP_MODELS = {"qwen3-embedding"}


@dataclass
class ProbeResult:
    name: str
    served_id: str | None
    latency_ms: float | None
    error: str | None


@dataclass
class ModelSummary:
    name: str
    served_id: str | None
    rounds_ok: int
    rounds_total: int
    median_latency_ms: float | None


def summarize(rounds: list[list[ProbeResult]]) -> list[ModelSummary]:
    """Collapse per-round probes into one summary per model name.

    Failed rounds count against availability but are excluded from the
    latency median -- scoring a failure as 0ms would make a broken model
    look like the fastest one.
    """
    by_name: dict[str, list[ProbeResult]] = {}
    for round_results in rounds:
        for result in round_results:
            by_name.setdefault(result.name, []).append(result)

    summaries = []
    for name, results in by_name.items():
        successes = [r for r in results if r.error is None]
        latencies = [r.latency_ms for r in successes if r.latency_ms is not None]
        summaries.append(
            ModelSummary(
                name=name,
                served_id=successes[0].served_id if successes else None,
                rounds_ok=len(successes),
                rounds_total=len(results),
                median_latency_ms=statistics.median(latencies) if latencies else None,
            )
        )
    return summaries


def group_by_served_id(summaries: list[ModelSummary]) -> dict[str, list[str]]:
    """served model id -> the NRP names that resolve to it.

    Models that never responded have no served id and are excluded.
    """
    groups: dict[str, list[str]] = {}
    for summary in summaries:
        if summary.served_id is None:
            continue
        groups.setdefault(summary.served_id, []).append(summary.name)
    return groups


async def list_models(api_key: str) -> list[str]:
    """Every chat model name NRP currently advertises."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{NRP_API_BASE}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
    return [m["id"] for m in resp.json()["data"] if m["id"] not in SKIP_MODELS]


async def probe_model(name: str, api_key: str) -> ProbeResult:
    """One timed chat call. Never raises -- a failure is a data point."""
    start = time.perf_counter()
    try:
        response = await litellm.acompletion(
            model=f"openai/{name}",
            messages=[{"role": "user", "content": PROBE_PROMPT}],
            max_tokens=PROBE_MAX_TOKENS,
            api_base=NRP_API_BASE,
            api_key=api_key,
            timeout=PROBE_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 - provider errors are opaque
        return ProbeResult(name=name, served_id=None, latency_ms=None, error=str(exc)[:200])

    return ProbeResult(
        name=name,
        served_id=response.model,
        latency_ms=(time.perf_counter() - start) * 1000,
        error=None,
    )


async def run(rounds: int) -> list[list[ProbeResult]]:
    """Probe every advertised chat model, `rounds` times.

    ponytail: rounds run sequentially. Probing in parallel would make the
    latency numbers meaningless, since NRP schedules these models on shared
    cluster hardware and concurrent probes would queue behind each other.
    """
    api_key = os.environ["NRP_API_KEY"]
    names = await list_models(api_key)
    print(f"Probing {len(names)} chat models x {rounds} rounds...\n")

    all_rounds = []
    for i in range(rounds):
        print(f"  round {i + 1}/{rounds}")
        all_rounds.append([await probe_model(name, api_key) for name in names])
    return all_rounds


def format_report(summaries: list[ModelSummary]) -> str:
    """Markdown: one row per model, plus the alias groups."""
    ordered = sorted(
        summaries,
        key=lambda s: (s.median_latency_ms is None, s.median_latency_ms or 0.0),
    )

    lines = ["# NRP Model Characterization\n"]
    lines.append("| NRP name | Served id | Availability | Median latency |")
    lines.append("|---|---|---|---|")
    for s in ordered:
        served = s.served_id or "—"
        latency = f"{s.median_latency_ms:.0f} ms" if s.median_latency_ms is not None else "—"
        lines.append(
            f"| `{s.name}` | `{served}` | {s.rounds_ok}/{s.rounds_total} | {latency} |"
        )

    lines.append("\n## Distinct models (deduplicated by served id)\n")
    groups = group_by_served_id(summaries)
    lines.append(f"**{len(groups)} distinct working models.**\n")
    for served, names in sorted(groups.items()):
        alias_note = f" (aliases: {', '.join(f'`{n}`' for n in names)})" if len(names) > 1 else ""
        lines.append(f"- `{served}`{alias_note}")

    dead = [s.name for s in summaries if s.rounds_ok == 0]
    if dead:
        lines.append("\n## Never responded\n")
        for name in sorted(dead):
            lines.append(f"- `{name}`")

    return "\n".join(lines)


def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    summaries = summarize(asyncio.run(run(rounds)))
    report = format_report(summaries)
    print("\n" + report)

    from pathlib import Path

    out = Path(__file__).resolve().parent.parent / "docs" / "nrp_characterization.md"
    out.write_text(report + "\n")
    print(f"\n[info] Wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_characterize.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Confirm `httpx` is importable**

`httpx` arrives via the `dev` extra (it is a `fastapi`/`TestClient` dependency) but is used here in non-test code. Verify:

```bash
.venv/bin/python -c "import httpx; print('ok')"
```

If this fails, add `httpx` to `[project].dependencies` in `pyproject.toml` and re-run `.venv/bin/pip install -q -e ".[dev]"`. If it succeeds, still add it to `[project].dependencies` — a runtime module must not depend on a dev extra.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, 55 passed.

- [ ] **Step 7: Commit**

```bash
git add gatoway/characterize.py tests/test_characterize.py pyproject.toml
git commit -m "Add NRP model characterization probe

Measures the inputs the wide ladder needs: served model id (so aliases
collapse -- three NRP names resolve to one served gemma-4-12B),
availability across rounds, and median latency as the observed check on
published parameter counts, which are unreliable for MoE models.

Not bench_latency.py, which stubs the provider call out by design.

Claude-Session: https://claude.ai/code/session_013J4bQFhu3pRp5TSwokHm5n"
```

---

### Task 4: Run the spike and fold findings into the design

**Files:**
- Create: `docs/nrp_characterization.md` (generated by Task 3)
- Modify: `docs/specs/2026-09-04-wide-ladder-design.md` §4.1, §4.2, §4.4, §8.1

**Interfaces:**
- Consumes: `gatoway/characterize.py` from Task 3.
- Produces: a rung table backed by measurement. Step 4 of the overall design (the wide ladder) builds directly on it.

- [ ] **Step 1: Run the probe**

```bash
.venv/bin/python -m gatoway.characterize 3
```

Three rounds, sequential, roughly 14 models each. Expect several minutes. It writes `docs/nrp_characterization.md`.

- [ ] **Step 2: Answer the persistent-vs-transient question**

`qwen3-4bit` and `gemma-small-e4b` each failed a single probe during the migration. Read the availability column:

- `0/3` → persistent. They stay excluded from the ladder; note it in §4.1.
- `1/3` or `2/3` → flaky. Still excluded from the ladder as primaries, but record the flakiness — a rung that disappears intermittently is a circuit-breaker concern, not just an inventory note.
- `3/3` → the migration failure was transient. Reconsider them as rungs and add their served ids to §4.1.

- [ ] **Step 3: Check the latency ordering against the param ordering**

This is the MoE check from design §4.4. Compare median latency rank against the §4.2 rung order (12B → 1T).

Write a short subsection in `docs/nrp_characterization.md` under a `## Latency vs parameter ordering` heading, stating for each model whether measured latency agrees with its param-based rung, and flagging any inversion. A model whose latency contradicts its param position by more than one rung is a candidate for re-costing by active rather than total params.

Do **not** re-cost the ladder in this task. Record the finding; the ladder change is design step 4, and it needs the trustworthy eval (step 3) to judge whether re-costing helped.

- [ ] **Step 4: Update the design doc's inventory and rung tables**

In `docs/specs/2026-09-04-wide-ladder-design.md`:

- §4.1: replace "from a live probe" with a reference to `docs/nrp_characterization.md` plus the run date, and correct any served id the probe reports differently.
- §4.2: if any rung's model turned out unavailable, drop it and say so; if a model previously excluded came back `3/3`, add it.
- §4.4: add a sentence stating whether measured latency confirmed or contradicted the param ordering, citing the characterization report.
- §8.1: change the three remaining bullets to `[x]` done, since this task closes them.

- [ ] **Step 5: Verify the report and the design agree**

Run:

```bash
grep -c '^| `' docs/nrp_characterization.md
```

Expected: one row per probed chat model (13, if NRP's inventory is unchanged and only `qwen3-embedding` is skipped). Confirm by eye that every model named in design §4.2 appears in the characterization table with availability better than `0/N`. A rung whose model never responded is a plan failure, not an acceptable result.

- [ ] **Step 6: Commit**

```bash
git add docs/nrp_characterization.md docs/specs/2026-09-04-wide-ladder-design.md
git commit -m "Characterize NRP models; back the rung table with measurement

Resolves the three open items in design SS 8.1: served-id deduplication,
availability across repeated rounds, and median latency per model as the
observed check on the MoE param-count risk.

Claude-Session: https://claude.ai/code/session_013J4bQFhu3pRp5TSwokHm5n"
```

---

## Done when

- `.venv/bin/pytest -q` passes with 55 tests.
- No `SPEC.md`, `TASKS.md` or `eval_report.md` at the repo root; `docs/spec.md` says v0.2 and mentions no Anthropic model, `VECTOR(1536)`, or ivfflat index.
- `docs/nrp_characterization.md` exists, with an availability and latency row per NRP chat model.
- Design §8.1's three bullets are checked off, and §4.2's rung table cites measured data.

**Not in scope** — these belong to later plans, gated on the eval rework:
- Changing `TIER_MODELS`, `router.py`, or `schema.sql`
- Adding context-window constants to `providers.py`
- Re-costing any model by active rather than total parameters
