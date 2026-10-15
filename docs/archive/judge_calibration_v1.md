# Live rubric judge calibration

> Historical calibration for the original prompt-only judge. It does not
> validate the new `rubric-json-v2` configuration. See
> [judge reliability](judge_reliability.md) for the successful targeted probe
> and the pending broader calibration.

## Result

**PASS — 24 task/judge combinations**, completed in 514.37 seconds.
The run used the configured NRP endpoint after explicit user authorization.

For each of 12 rubric-scored tasks, both openai/kimi and openai/glm-5 graded
the checked-in reference answer and the non-answer “I don't know.”
Every reference scored **at least 0.8**, and every non-answer scored
**at most 0.2**. This is 48 scored answers; the test output does not report
whether any malformed-output retries occurred.

| Split | Task | Kimi | GLM-5 |
|---|---|---|---|
| Train | shared_database_split | PASS | PASS |
| Train | database_column_rollout | PASS | PASS |
| Train | infinitely_many_primes | PASS | PASS |
| Train | sum_first_odd_numbers | PASS | PASS |
| Train | distributed_rate_limiter | PASS | PASS |
| Train | order_pipeline | PASS | PASS |
| Train | pastebin | PASS | PASS |
| Train | tenant_isolation | PASS | PASS |
| Eval | multistep_planning | PASS | PASS |
| Eval | hard_math_proof | PASS | PASS |
| Eval | auth_extraction | PASS | PASS |
| Eval | url_shortener | PASS | PASS |

## Reproduction

~~~bash
GATOWAY_LIVE_TESTS=1 .venv/bin/pytest -q tests/test_judge.py -k live_rubric_calibration
~~~

Result: 24 passed, 12 deselected in 514.37s (0:08:34).

Each rubric item receives a boolean judgment. The score is the fraction of
criteria satisfied. Temperature is zero; the judge response budget is 1024
tokens with a 60-second timeout. Malformed JSON permits one retry.
Production selects GLM-5 for answers actually produced by Kimi and Kimi for
other answer models. Calibration explicitly exercises both judge choices.

## Scope

This checks whether both judges distinguish clear reference answers from
clear non-answers. It does not establish consistency on partial answers,
resistance to adversarial instructions, or agreement with human graders.
No routing performance was measured and no database rows were written.

## Bootstrap runtime follow-up

The measured bootstrap exposed truncated judge JSON and slow provider calls.
Current judge settings retain the initial 1024-token allowance, with a
120-second timeout. A truncated response permits one 4096-token retry with a
240-second timeout; other malformed responses retain the initial allowance.
Malformed output is never accepted as a score. The calibration above used the
original settings and was not repeated after these runtime changes.
The measured bank now contains all 288 observations; see bootstrap_report.md.
