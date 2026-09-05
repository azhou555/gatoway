"""Pure analysis half of the NRP characterization probe.

The network half (probe_model/run) is not unit-tested -- it is a thin
litellm call. Everything that can get the answer *wrong* lives in
summarize()/group_by_served_id()/format_report(), so that is what is tested.
"""

from gatoway.characterize import (
    ModelSummary,
    ProbeResult,
    format_report,
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


def test_format_report_rows_and_ordering():
    """Mirrors Task 4 Step 5's `grep -c '^| \\`'` row count.

    format_report() is what Task 4 verifies against, so its sort key,
    alias-note branch and dead-model section need a check here rather than
    surfacing halfway through a multi-minute live probe.
    """
    report = format_report(
        [
            ModelSummary("slow", "v/S", 3, 3, 900.0),
            ModelSummary("fast", "v/F", 3, 3, 100.0),
            ModelSummary("dead", None, 0, 3, None),
        ]
    )
    assert report.count("\n| `") == 3  # data rows only; header row starts "| N"
    assert report.index("`fast`") < report.index("`slow`") < report.index("`dead`")
    assert "## Never responded" in report
