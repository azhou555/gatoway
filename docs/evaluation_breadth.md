# Expanded evaluation coverage

`python -m gatoway.eval --suite expanded` selects 32 held-out tasks. The default
`--suite legacy` retains the existing 16. New results are a separate baseline:
new judge configuration, new tasks, and a different task mix must be named.

## Added tasks

| Session | Task | Capability |
|---|---|---|
| structured | invoice_extraction | Distinguish subtotal from total; currency/unit extraction |
| structured | missing_fields | Preserve missing values without inventing facts |
| structured | injected_document | Treat malicious instructions inside source text as data |
| structured | latest_status | Select time-ordered evidence for the right entity |
| structured | stable_dedup | Normalize values while preserving first occurrence |
| structured | aggregate_events | Apply signed events and group totals |
| structured | priority_classification | Follow ordered rules with overlapping conditions |
| structured | exact_output_contract | Filter/sort values and obey an exact output contract |
| reasoning | discount_tax | Apply discounts, tax, and shipping in the specified order |
| reasoning | weighted_average | Weight unequal groups correctly |
| reasoning | schedule_constraints | Solve precedence and adjacency constraints |
| reasoning | capacity_planning | Choose the optimal capacity-constrained job subset |
| reasoning | interval_boundaries | Respect half-open interval endpoints |
| reasoning | logic_entailment | Distinguish necessary conclusions from unsupported ones |
| reasoning | answerability | Abstain when evidence does not answer the question |
| reasoning | long_context_override | Select the latest relevant record among 80 distractors |

These are two additional independent eight-turn sessions. All additions use
strict JSON value matching, not an LLM judge. Key order and equivalent JSON
numbers are accepted; extra/missing keys, wrong types (including boolean versus
number), reordered arrays, duplicate keys, non-JSON constants, prose, and code
fences fail. Prompts explicitly require JSON-only output. This measures both
correctness and structured-output compliance, not correctness alone.

No new task is copied into the training bank. The source overlap guard now
checks all 32 eval prompts. Tests validate gold answers, false-positive cases,
independently enumerate optimization/scheduling solutions, and exercise session
boundaries and stability-gate inclusion. Three dry-run repetitions passed;
this is harness validation, not measured model performance.

## Routing evidence

An offline DB-backed density probe against `gatoway_eval_measured_20260930`
found evidence on all eight rungs for the original 16 tasks and six of the 16
new tasks: **22/32 total**. Ten new tasks have no qualifying neighbors; one
additional task has neighbors but none meets its session effectiveness bar.
Thus **11/16 new tasks select the explicit fallback**. This is a useful
out-of-bank generalization challenge, not yet a broad test of learned routing.

Local artifacts: `artifacts/judge_v2/expanded_density.json` and `.md`.
Use separate paths to preserve the original density report:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m gatoway.bank_density \
  --database gatoway_eval_measured_20260930 --suite expanded \
  --output artifacts/expanded_density.json --report artifacts/expanded_density.md

.venv/bin/python -m gatoway.eval --dry-run --suite expanded --runs 3 \
  --checkpoint artifacts/expanded_smoke.json --report artifacts/expanded_smoke.md
```

After judge calibration and an explicit decision about bank/scorer versions,
a fresh live run can use `--suite expanded --require-db --database ...` with a
new checkpoint and report path. The expanded suite needs 192 answer generations
and 24 rubric judgments across three repetitions, before retries. The 16 new
tasks add no judge calls. The first three-run live comparison completed on
October 4 against the frozen historical bank: structured-task quality was
91.7% routed versus 100% baseline; reasoning-task quality was 87.5% versus
100%. Capacity planning failed all three routed attempts, and injected-document
extraction failed twice through refusals. See [the completed report](eval_report_expanded.md).

## Remaining breadth limitations

32 handcrafted tasks are a starting point, not a representative production
sample. The longer-context case contains only 80 distractor records; it is not
a 100K-token stress test. The existing three-task agentic benchmark is unchanged.
Next steps are multiple independent instances per capability, harder coding and
repository-level tasks, representative user workloads, and a separate untouched
holdout after any tuning. To measure learned routing across the new categories,
add distinct training tasks and bootstrap a new bank; never seed with these
held-out prompts. Preserve the frozen-bank generalization result separately.
