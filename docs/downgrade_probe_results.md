# Downgrade-safety probe results — October 5, 2026

Validation of the downgrades `strict_evidence` (the gated `GATOWAY_STRICT_ROUTING`
rule) would make, on fresh tasks the bank has never seen, plus a re-grading of
the October 4 screening that changes what the "next improvement" should be.

Raw generator output: `docs/policy_results_probe.md` (artifacts
`artifacts/policy_eval_probe_20261005`). That report now shows both the strict
raw score (probe group −50, a code fence counts as a miss) and the
fence-normalized score (0.0, capability); **this file is the interpreted
verdict** that explains the gap and its production consequence.

## 1. The probes: both robust downgrades reason correctly on fresh instances

`strict_evidence` downgrades five tasks off Kimi. Two have high-similarity
training coverage and were probed with 30 fresh, objectively-answerable tasks
(15 each, answers computed by executing the spec, no bank leakage — worst
similarity 0.58; each routes to its cheap rung, verified by `--prepare-only`):

| Cluster | Cheap rung | Correct, fence-normalized (×3 reps) | Kimi |
|---|---|---:|---:|
| code_fix (off-by-one loop) | glm-5 | 45/45 (100%) | 100% |
| sql_query (top-two distinct) | gemma-small | 45/45 (100%) | 100% |

**What this shows and does not show.** The cheap rung reasons correctly about
fresh instances of these problems — as well as Kimi. It does **not** show the
cheap rung can produce the original artifact: the real `code_fix`/`sql_query`
tasks are graded by `python_execution`/`sql_execution` (write code / write SQL),
while these probes ask for the computed result as JSON. Both sides scoring 100%
is also a ceiling that cannot rank the models. So: reasoning on these clusters
is validated on fresh inputs; code/SQL *generation* still rests on one original
task each. The three gpt-oss downgrades could not be probed at all — JSON-framed
siblings drift out of the gpt-oss evidence neighborhood (the framing differs from
the originals' "export function … fenced typescript"), so this run says nothing
about them either way.

## 2. The bigger finding: output fencing, and what it means for the next fix

The probe grader scored gemma-small at 0% because it returns the **correct**
value wrapped in a ```json fence; `score_json` parses the whole response
strictly. Re-grading the October 4 screening with fences normalized for every
tier (offline, no inference):

| Suite (`json_exact`) | current vs Kimi, raw | fence-normalized |
|---|---:|---:|
| holdout_reasoning | −25.0 | −12.5 |
| holdout_structured | −25.0 | −12.5 |
| reasoning | −12.5 | −12.5 |
| structured | −12.5 | −12.5 |
| **overall (json_exact)** | **−18.8** | **−12.5** |

Fence rate by tier among `json_exact` responses: gemma-small 6/24 (25%),
gpt-oss 2/87, Kimi 2/96, glm-5 0/6.

Two takeaways:
- **Fencing is a real, existing production issue under the current router**, not
  just a strict precondition. gemma-small — which the *current* router selects
  51/144 times — fences a quarter of its structured answers. A caller expecting
  JSON gets a fenced string today.
- **But format is not the whole story.** A −12.5-point capability gap survives
  normalization across every `json_exact` suite. Strict routing's quality case
  is weakened on the holdout (half of that loss was format) but not eliminated.

## 3. Recommendations

**Do first — cheapest real win, independent of any flip:** add response
normalization (strip code fences / extract JSON) in the gateway output path.
Raw instruction-following still matters, but a fenced-but-correct answer should
not be served as-is. This helps the **current** router most (gemma-small: 51
routes under current vs 3 under strict) and recovers ~6 points on the json_exact
holdout immediately. This better answers the original "next improvement"
question than flipping strict does.

**On the flip (`GATOWAY_STRICT_ROUTING`):**
- The gate is a single boolean. Flipping it enables **all five** downgrades,
  including the three gpt-oss ones, whose only evidence remains the original
  screening (3 tasks × 3 reps, coding +3.47 vs Kimi) — not fresh-validated.
- The two robust downgrades (glm-5, gemma-small) now have fresh-task evidence
  that the cheap rung reasons correctly; the gemma-small one additionally
  requires the output normalization above to be serve-safe.
- Enabling only the validated downgrades would require per-rung control the gate
  does not have (see the ponytail note in `router.py`). Do not add that knob
  without deciding it is wanted.

## 4. Follow-ups

- Make `score_json` fence-tolerant; as written it conflates format with
  correctness and mis-scores any fence-wrapping model across all json suites.
- Densify the bank's coding coverage so the gpt-oss clusters can be probed and
  generalize; today they are too narrow to validate.
