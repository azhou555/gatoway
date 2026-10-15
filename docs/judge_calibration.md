# Live judge calibration — rubric-json-v2

## Observed output reliability

The approved live calibration completed **54/54 judgments with valid JSON on
the first attempt**, zero retries, and zero infrastructure failures. Total
judge time: **587.19 seconds**; output tokens: **6,836**. This is one corpus pass,
not an estimate of reliability on arbitrary future inputs.

| Actual judge | Judgments | Median call time | Maximum call time | Output tokens |
|---|---:|---:|---:|---:|
| GLM-5 | 27 | 0.94s | 80.72s | 499 |
| Kimi | 27 | 13.79s | 31.91s | 6,337 |

Schema-constrained output is enabled for both models; GLM-5 uses low reasoning
effort. Limits are 1024 tokens / 120 seconds initially, with one 4096-token /
240-second retry. Final content only is scored. No retries were needed here.
The answer_model field in raw records determines the other model used as judge;
the attempt.model field names the actual judge.

## Quality checks

| Cases | Result |
|---|---|
| Reference answers | 23/24 met the >=0.8 threshold |
| Nonanswers | 24/24 met the <=0.2 threshold |
| Hand-authored partial answer | Both judges scored 0.4, as expected |
| Instruction-injection answer | Both judges scored 0.0, as expected |
| Previously blocked saved answer | Both returned valid judgments, scoring 0.4 |

**Original calibration gate: FAIL — one quality failure, no infrastructure failures.**
The saved regression answer has no independent gold score; its check is output
validity only. Thus the 54 judgments contain 52 semantic checks and two format
regression checks.

The failure was multistep_planning/reference: GLM-5 marked all four criteria
true (1.0); Kimi marked the outbox-explanation and data-validation criteria
false (0.5). The original brief answer named an outbox but did not explain its
transactional mechanism, and did not explicitly validate data before switching
stores. The discrepancy exposes ambiguity in the reference and a difference
in judge strictness. It must not be hidden by changing the score threshold.

## Corrected reference follow-up

A separate calibration anchor now explicitly describes transactional outbox
writes, idempotent delivery, validation before cutover, incremental compatible
traffic migration, and a concrete rollback route. It lives in
benchmarks/judge/migration_reference.txt. The historical benchmark's canned
answer, rubric, and model-generated evaluation answers remain unchanged.

The corrected anchor scored **1.0 in all six judgments**: three repetitions on
each judge. All six returned valid JSON on the first attempt, with no retries
or infrastructure failures. Total judge time: **72.05 seconds**; output tokens:
**1,130**. This is a targeted recheck, not a rerun of the entire 54-call corpus.
Both the original failed record and the follow-up are preserved.

## Reproduction and artifacts

```bash
# Full current calibration corpus; choose a new path each time
.venv/bin/python -m gatoway.judge_calibration --runs 1 \
  --output artifacts/judge_v2/calibration_next.json

# Targeted repeatability check
.venv/bin/python -m gatoway.judge_calibration \
  --case multistep_planning/reference --runs 3 \
  --output artifacts/judge_v2/migration_reference_next.json
```

Saved records (ignored by Git):

- artifacts/judge_v2/calibration.json — original 54 judgments, including failure.
- artifacts/judge_v2/migration_reference_recheck.json — six corrected-anchor checks.
- artifacts/judge_v2/probe_result.json — earlier targeted configuration probe.

The records contain scorer/input signatures, criterion booleans, timing,
tokens, finish reasons, and errors. The corrected anchor changes the input
signature; the judge implementation is unchanged between these two runs.

The earlier prompt-only judge's calibration is archived in
[judge_calibration_v1.md](archive/judge_calibration_v1.md).

## Implications

The observed formatting blocker is resolved on this corpus, including the
previously failing answer. Grading agreement on ambiguous or borderline
answers is not established; the original migration reference disagreement
shows why additional labeled partial answers and human review remain useful.
No routing-bank scores or historical evaluation scores were changed.
The next live comparison needs a new checkpoint/report for the new scorer,
with an explicit frozen-bank or audited bank-regrading policy.

## Follow-up on actual generated answers — 2026-10-04

The three-run expanded evaluation completed all 24 required rubric judgments,
but only 21/24 were valid on the first attempt. There were 29 attempts,
including five truncated outputs while Kimi graded routed planning answers.
One case exhausted its two configured attempts and required a checkpointed
resume; it succeeded after two more attempts on the same saved answer. All
failures remain in the per-run judge audit. Judge time totaled 930.8 seconds.

Thus the 54/54 calibration result did not establish first-attempt reliability
on actual generated answers. The final evaluation has no missing grades, but
its recovery history must accompany reliability claims. See
[the expanded evaluation](eval_report_expanded.md). No judge settings were
changed during that evaluation.
