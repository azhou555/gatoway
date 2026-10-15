# Measured bank bootstrap — 2026-09-30

**Complete: 288 measured observations, with no missing model/prompt pairs.**
The isolated database `gatoway_eval_measured_20260930` contains 36 train
prompts evaluated on all eight primary models. No hand-labeled seed rows were
copied. The original `gatoway` database still contains 106 rows, unchanged.

Generation and rubric judging used `https://ellm.nrp-nautilus.io/v1` after
explicit user authorization. Embeddings and Docker code grading ran locally.

## Integrity and density

Saved outcomes and database rows agree on all scores and measured difficulties.
Every row has confidence 1 and no session ID. Stable IDs prevent duplicates.
Current task/scorer fingerprints match every accepted checkpoint.
All 16 held-out eval tasks have qualifying evidence on all eight rungs under
the production neighbor query; no density-probe decision fell back.
See [the density report](bank_density.md).

| Model | Observations | Mean score | Zero scores | Full scores | Token-limit finishes |
|---|---:|---:|---:|---:|---:|
| gemma-small | 36 | 0.8542 | 3 | 28 | 5 |
| qwen3-small | 36 | 0.8542 | 5 | 30 | 12 |
| gpt-oss | 36 | 0.8583 | 3 | 27 | 11 |
| qwen3 | 36 | 0.8444 | 4 | 29 | 11 |
| minimax-m2 | 36 | 0.7167 | 8 | 23 | 16 |
| deepseek-v4-flash | 36 | 0.7264 | 8 | 22 | 17 |
| glm-5 | 36 | 0.9292 | 1 | 30 | 16 |
| kimi | 36 | 0.9292 | 1 | 30 | 6 |

These scores measure the checked-in tasks under fixed output allowances:
512 tokens for original tasks and 2048 for coding/design tasks. There were
94 token-limit finishes. The constrained legacy loop format and the provider's
reasoning-content fallback also affect scores. These are not unrestricted
model capability rankings.

## Corrections made during bootstrap

- Fixed the database ownership-marker lookup to use PostgreSQL's shared
  object catalog; verified close/reopen behavior with a disposable database.
- Normalized Unicode mathematical minus in exact matching. Three correct
  negative-temperature answers were regraded from saved responses.
- Clarified the third-salary training prompt to require exactly one column
  named salary. Archived its eight earlier responses, removed only those
  superseded isolated-bank rows, and regenerated that training task.
- Preserved raw generations before judging, so judge failures can resume
  without regenerating answers. Truncated judge output gets one larger retry;
  malformed output still raises instead of producing a score.
- Corrected the TypeScript RPN zero fixture to accept numeric negative zero.
  Regraded its eight saved responses in Docker; four scores improved from
  5/6 to 1. The two missing/truncated exports remained failures.
- Increased generation timeouts from 60 to 120 seconds and retried the four
  missing provider pairs. All recovered. Judge calls use 120 seconds initially
  and 240 seconds for the conditional larger retry.

Earlier checkpoints and source snapshots were retained before corrections.
Each fingerprint migration records which prior outcomes were reused or
regraded. Local artifacts include fixture_correction_audit.json,
judge_retry_correction_audit.json, runtime_correction_audit.json,
bank_integrity.json and density.json under
artifacts/gatoway_eval_measured_20260930/. Artifacts include model answers and
are ignored by Git.

## Validation

The final ordinary suite passed **340 tests**, with 28 opt-in tests skipped
and two existing dependency deprecation warnings. Separate local Docker and
Postgres integration checks passed. Earlier live judge calibration passed all
24 task/judge cases; its scope and subsequent runtime changes are recorded in
[the calibration report](judge_calibration.md).

The held-out three-run gate uses this frozen measured bank; its outcome is
reported separately in [the evaluation report](eval_report.md).
