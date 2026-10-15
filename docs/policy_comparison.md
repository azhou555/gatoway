# Routing policy screening — October 4, 2026

Status: complete — 342/342 unique outcomes scored, covering seven policies on 48 tasks × three repetitions. [Results](policy_results.md). Production routing is unchanged.

The experiment compares five fixed candidates with the current gateway and always-Kimi. Decisions use the frozen 288-row training bank, never evaluation answers or labels. Three fresh repetitions cover the existing 32 tasks and 16 newly authored objective tasks. The new holdout covers structured extraction and reasoning; it is not a fresh coding or open-ended holdout and cannot establish general production quality.

| Policy | Decision rule |
|---|---|
| Current | Existing parameter-order router; minimum two neighbors, similarity >=0.3, session-adjusted mean-quality bar; GPT-OSS fallback. |
| Frontier fallback | Current routing, except insufficient evidence defaults to Kimi. |
| Paired quality | Parameter order; at least three neighbors at similarity >=0.3 with candidate and Kimi observations on the same training prompts; candidate mean meets the absolute bar and paired mean quality is at least Kimi's; Kimi fallback. |
| Price order | Current absolute evidence requirements, with candidates ordered by estimated input cost plus 1,024 expected output tokens; GPT-OSS fallback. |
| Strict evidence | Parameter order; at least three neighbors at similarity >=0.4, each scoring >=0.95; Kimi fallback. |
| Paired price | At least three paired neighbors at similarity >=0.4; absolute bar met and no individual candidate score below Kimi; price order; Kimi fallback. |
| Always Kimi | Baseline for every task. |

These are heuristics to screen, not calibrated guarantees. In particular, three training observations do not establish statistical quality equivalence. Historical bank labels retain their earlier generation budgets and scoring; evidence quality remains a limitation. The two strict variants happen to choose identical models on all 48 tasks.

Every answer uses temperature 0 and an 8,192-token output cap, including the current-router control. This isolates policy differences within the new experiment; comparisons with the previous 512/2,048-token experiment conflate output budget and new generations. Truncated outputs remain in the results and are counted. No reasoning-content fallback is accepted as a final answer.

Policies selecting the same model share its answer and score within a task/repetition. Each repetition makes new calls. This reduces inference work and gives a paired comparison, but means policy results are correlated. Calls are shuffled deterministically and concurrency is three. Provider-call durations exclude judging and routing overhead and are not end-to-end gateway latency. No cross-model provider fallback occurs.

Pricing uses the saved OpenRouter catalog, with the user-proposed Gemma 4 12B rates ($0.13/M input, $0.40/M output) explicitly marked as an unverified assumption. Results are estimated uncached token costs, not NRP bills. Judge overhead is recorded separately and excluded from answer costs. Unknown usage on failed requests cannot be priced.

The runner checkpoints every answer and score. Provider/scorer errors remain missing, rather than being converted to quality failures or silently dropped from coverage. A partial report compares only pairs with both scores available and is not a completed gate. Resuming reuses saved answers and retries unresolved work. The manifest freezes source hashes, pricing, routing evidence, bank hash and generation controls.

Results will distinguish existing-suite diagnostics from the fresh holdout, report category deltas, model selections, truncation counts, and paired mean-score differences. The 95% intervals use a task-cluster bootstrap, retaining all repetitions per sampled task (2,000 resamples, fixed seed). They are exploratory, unadjusted for multiple policy comparisons, and do not prove equivalence. No policy is automatically promoted based on this screening run.

Reproduce or resume:

```sh
HF_HUB_OFFLINE=1 python -m gatoway.policy_eval \
  --output artifacts/policy_eval_20261004
```

Use a new output directory after any change to source, benchmark, pricing or run count. Raw artifacts are local and ignored by Git.

Recovery, after the main process exits:

```sh
HF_HUB_OFFLINE=1 python scripts/recover_policy_eval.py artifacts/policy_eval_20261004
python scripts/report_policy_eval.py artifacts/policy_eval_20261004 --output docs/policy_results.md
```

Recovery extends the client timeout from 240 to 600 seconds with the same generation controls. Original errors remain in the audit. Timeout attempts without usage are excluded from monetary estimates and successful-call timing.

Rubric grading uses GLM for Kimi answers and Kimi for other answers to avoid self-grading. This introduces a possible judge-model confound; the fresh holdout uses objective JSON grading.

Post-run verification confirmed that all 288 training-bank rows were unchanged. The final source hash also matched the frozen manifest. Validation: 395 tests passed, 28 skipped.
