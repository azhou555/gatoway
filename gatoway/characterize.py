"""NRP model characterization probe.

Produces the measured inputs the wide model ladder is built from, per
docs/specs/2026-09-04-wide-ladder-design.md § 8.1:

  - served model id, so aliases collapse (three NRP names resolve to one
    served gemma-4-12B; a ladder built off /v1/models without deduplicating
    would have phantom rungs)
  - availability across repeated rounds (two models failed a single probe
    during the migration -- persistent or transient?)
  - median latency per model, the observed second signal against the
    published parameter count, which is unreliable for MoE models where
    total and active params disagree

This is deliberately NOT gatoway/bench_latency.py: that benchmark stubs the
provider call out to an instant stand-in, because spec § 9 excludes provider
latency from the gateway's overhead budget. It measures the opposite thing.

Usage:
    python -m gatoway.characterize [ROUNDS]   # default 3
"""

from __future__ import annotations

import asyncio
import datetime
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


# Generated into every report, not written by hand: a hand-added footer would
# be destroyed by the same re-run it exists to warn about. Analysis lives in
# the design doc because it has to outlive the numbers that produced it --
# prose describing run 1 sitting above run 3's table is silently wrong, which
# is worse than losing it loudly.
PROVENANCE_TEMPLATE = """
---

Generated by `python -m gatoway.characterize` on {date} — {rounds} rounds over
{models} advertised chat models (`qwen3-embedding` skipped, not a chat model).

**This file is disposable. Edit nothing here; a re-run overwrites it.** What a
run *means* belongs in `docs/specs/2026-09-04-wide-ladder-design.md` §4.1 and
§4.4.
"""


def format_report(summaries: list[ModelSummary]) -> str:
    """Markdown: one row per model, the alias groups, and a provenance footer."""
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

    lines.append(PROVENANCE_TEMPLATE.format(
        date=datetime.date.today().isoformat(),
        rounds=max((s.rounds_total for s in summaries), default=0),
        models=len(summaries),
    ))
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
