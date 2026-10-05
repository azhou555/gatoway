# Judge reliability: rubric-json-v2

> Subsequent live evaluation completed all 24 rubric judgments, but only
> 21 were valid on the first attempt. Five truncated attempts occurred;
> one judgment required a checkpointed resume after exhausting both attempts.
> See [the expanded evaluation audit](eval_report_expanded.md).

The previous GLM-5 judge twice failed on the same saved authentication-design
answer, emitting truncated reasoning instead of JSON even after its 4096-token
retry. Increasing timeouts alone did not fix it.

## Implemented

- Request a strict JSON schema: one boolean per rubric item, no extra fields.
- Set GLM-5 reasoning effort to `low` through `chat_template_kwargs`.
- Read final answer content only; reasoning-content fallback is disabled for
  judges, while normal answer generation retains its previous behavior.
- Validate locally even when the server accepts the schema. Reject truncation,
  nonboolean values, duplicate fields, extra fields, and wrong array lengths.
- Make at most two attempts with the same judge (1024/4096 tokens,
  120/240-second timeouts), retrying the original request rather than feeding
  truncated reasoning back. Provider/format failures never become zero scores.
- Version the configuration and expose per-attempt timing, token counts,
  finish reasons, errors, and criterion decisions to calibration.

Judge selection remains Kimi, with GLM-5 judging answers produced by Kimi.
No silent substitution or unconstrained fallback is used.

NRP documents GLM-5's default maximum effort and low-effort control in its
[model catalog](https://nrp.ai/documentation/userdocs/ai/llm-managed/models/).
LiteLLM documents the schema request format in
[structured outputs](https://docs.litellm.ai/docs/completion/json_mode).

## Evidence so far

A live probe of the exact saved answer that blocked repetition two returned
valid final JSON in **2.45 seconds, 67 output tokens, finish_reason=stop** with
schema constraints and low effort. It returned `[false,false,true,true,false]`.
The probe allowed 4096 tokens; the implemented judge begins at 1024, with a
4096 retry. This is a targeted configuration probe, not a completed production
configuration calibration or a human-verified correctness result.

The fixture is checked in at `benchmarks/judge/truncated_auth_answer.txt`.
Probe artifacts are under `artifacts/judge_v2/`. The historical bank and eval
scores were not changed.

## Live calibration

```bash
.venv/bin/python -m gatoway.judge_calibration --runs 1 \
  --output artifacts/judge_v2/calibration_next.json
```

One pass contains **54 judgments**: 12 rubric tasks × reference/non-answer ×
two judges (48), plus a hand-authored partial answer, an instruction-injection
answer, and the saved regression answer, each on both judges (6). The partial
answer is expected to satisfy exactly the authorization-separation and token
validation/rotation criteria (2/5). The injected instructions earn no credit.
The saved regression checks valid grading only; it has no independent gold score.

The command records every result before continuing. It distinguishes quality
failures from infrastructure failures, reports first-attempt validity and retry
recovery, refuses to overwrite an existing output, and fails if either type
of failure occurs. `--runs 3` repeats the corpus to measure variation. Successful
parsing alone is insufficient: references must score >=0.8, nonanswers <=0.2,
and labeled partial/injection fixtures must match their expected scores.

After explicit user approval, the live run completed all **54 judgments**:
54 valid first attempts, no retries, and no infrastructure failures. It took
587.19 seconds and used 6,836 output tokens. One quality check failed: Kimi
scored the original migration reference 0.5 while GLM-5 scored it 1.0. Inspection
found that the reference did not explicitly explain atomic outbox writes or
pre-cutover data validation, despite those rubric requirements.

The calibration now uses a separate complete reference for that case; neither
the rubric, threshold, judge configuration, nor historical benchmark answer
was changed. The corrected reference scored 1.0 on both judges in all three
repetitions (6/6), all valid on the first attempt. The original 54-call run
remains a recorded quality-gate failure, not retroactively a pass. The full
54-call corpus has not been rerun with the corrected reference.

Both judges scored the hand-authored partial answer at 0.4, the injection
answer at 0.0, and the previously blocking saved answer at 0.4. The last is
a format/regression check, not a human gold-label check. See the full
[calibration record](judge_calibration.md). These observations support the
formatting fix but do not establish general grading agreement on ambiguous
answers; the original reference disagreement remains evidence of that limit.

## Before claiming reliability or restarting the comparison

1. The initial live calibration and corrected-reference recheck are complete.
   Preserve both records and distinguish their coverage when reporting results.
2. Inspect criterion agreement and repeat the difficult/partial cases. A small
   passing calibration cannot guarantee reliability on arbitrary answers.
3. Use a fresh versioned evaluation checkpoint/report. Existing checkpoint
   fingerprints intentionally reject changed scorer/source configurations.
   Do not copy old scores into a v2 report.
4. Decide explicitly whether to keep the historical routing bank frozen as a
   historical policy, or regrade its saved rubric-scored training answers into
   a new isolated bank. A scorer migration needs an audit; do not overwrite the
   existing 288 observations or regenerate answers just to obtain better scores.
5. The three-run expanded comparison completed October 4 using fresh checkpoints
   and the unchanged historical bank. Its generated planning answers exposed
   truncated judge output despite the calibration success. Add these failures
   to future judge stress tests. Output-budget effects on answer generation
   remain a separate controlled experiment; this change only alters judging.
