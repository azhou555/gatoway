# Plan: adopt the validated strict routing rule in router.py

## Goal

Make production routing match the only quality-safe candidate from the policy
screening (`strict_evidence` / `paired_price`): raise the confident-downgrade
bar and send low-evidence requests to the frontier model instead of a cheap
rung. Expected live effect: ~90% of requests route to Kimi, a small set of
well-evidenced tasks downgrade. This trades ~9% more cost than today's router
for ending the measured −14-point quality loss.

## The rule being ported (from `routing_policies.select`, strict path)

- Similarity floor `0.4` (was `0.3`).
- At least `3` primary-model neighbors per rung (was `2`).
- Every qualifying neighbor scores `>= 0.95` (new gate; today only the mean is checked).
- Mean still `>= bar` (threshold-adjusted, unchanged).
- Evidence is **primary-only**: a rung is judged by observations of `rung.primary`,
  not by fallback models folded in via `MODEL_RUNG_NAMES`.
- Insufficient evidence / below floor -> fall back to **Kimi**, not gpt-oss.

## Changes — `gatoway/router.py`

- [ ] `CONFIDENCE_FLOOR = 0.3 -> 0.4`
- [ ] `MIN_OBSERVATIONS = 2 -> 3`
- [ ] Add `MIN_NEIGHBOR_EFFECTIVENESS = 0.95`
- [ ] Add `LOW_EVIDENCE_FALLBACK_RUNG = "kimi"` (keep `FALLBACK_RUNG = "gpt-oss"`
      as the generic default used by circuit_breaker/app — do NOT repoint it).
- [ ] `fallback_rung_for_tokens`: use `LOW_EVIDENCE_FALLBACK_RUNG`; when it does
      not fit the context, return the most-capable capable rung (`capable[-1]`)
      instead of the cheapest (`capable[0]`), so the oversized edge stays a
      frontier choice. `# ponytail: >131k inputs fall to the largest-window rung; revisit only if huge requests become common`
- [ ] `decide()` rung loop:
      - group evidence primary-only (`observation.model_id == rung.primary`),
        replacing the `MODEL_RUNG_NAMES` pooling for the promotion decision;
      - add per-neighbor gate `all(e >= MIN_NEIGHBOR_EFFECTIVENESS ...)` alongside
        the existing mean check;
      - both low-evidence return sites already call `fallback_rung_for_tokens`,
        so they inherit the Kimi fallback — no extra change.

## Changes — coupled modules

- [ ] `gatoway/routing_policies.py:27`: replace `CONFIDENCE_FLOOR` with literal
      `0.3` for the non-strict floor, so the frozen screening re-runs unchanged.
- [ ] `gatoway/bank_density.py`: no code change — it re-exports the bumped
      constants, so coverage now measures against the real routing bar. Confirm
      its tests still pass with the new thresholds.

## Tests — `tests/test_router.py`

- [ ] Rewrite `test_shared_gemma_fallback_evidence_counts_for_qwen3_small_rung`
      to assert the **opposite**: fallback-model observations do NOT promote a
      rung (primary-only).
- [ ] Update the three fallback-tier assertions (lines ~108, ~134, ~143) from
      `FALLBACK_RUNG` to the Kimi low-evidence fallback.
- [ ] Fix fixtures that assumed 2 neighbors promote (line ~51) to use 3.
- [ ] Add: a neighbor below 0.95 blocks promotion even when the mean clears the bar.
- [ ] Add: oversized-beyond-Kimi input falls to the most-capable capable rung.

## Verification

- [ ] `.venv/bin/python -m pytest tests/test_router.py tests/test_routing_policies.py
      tests/test_bank_density.py tests/test_app.py` green.
- [ ] Full suite (`395 passed, 28 skipped` baseline) stays green.
- [ ] Spot-check `circuit_breaker.py` default rung is still `gpt-oss` (unchanged).

## Open decision for the user — ship live, or gate?

The screening report explicitly promotes **no** policy and asks for fresh-task
validation of the proposed downgrades first. This change flips live routing to
near-always-Kimi. Two options:
  1. Merge as the new production default now (simplest; accepts the report's
     caveat that only 16 fresh structured/reasoning tasks backed it).
  2. Land the code but keep it behind validation: re-run `bank_density` + a fresh
     coding/open-ended eval before flipping, per the report's "next validation".
Recommend (2). Decide before implementation.

## Review (implemented — land-and-gate, reversible)

Approach changed per "land and gate, don't make a change we can't revert":
the strict rule ships behind env flag `GATOWAY_STRICT_ROUTING`, default OFF.
With the flag unset the router is byte-for-byte unchanged, so this is NOT a
production behavior change yet — it is dormant code. Revert = unset the flag
(or `git revert`), no data migration.

Because `CONFIDENCE_FLOOR`/`MIN_OBSERVATIONS` are no longer mutated, the
coupled edits dropped out entirely:
- `routing_policies.py` — NOT touched (its non-strict floor stays 0.3).
- `bank_density.py` — NOT touched (still measures current coverage).
- existing `test_router.py` tests — NOT touched (they prove flag-off == today).

Changes made, all in `gatoway/router.py`:
- `STRICT_ROUTING` flag + `_env_flag()` reader; strict constants
  `STRICT_CONFIDENCE_FLOOR=0.4`, `STRICT_MIN_OBSERVATIONS=3`,
  `MIN_NEIGHBOR_EFFECTIVENESS=0.95`, `LOW_EVIDENCE_FALLBACK_RUNG="kimi"`.
- `PRIMARY_RUNG_NAMES` (primary-only evidence map).
- `fallback_rung_for_tokens`: frontier fallback + most-capable (`capable[-1]`)
  oversized substitute under strict; unchanged otherwise.
- `decide()`: floor/min-obs/rung-map/per-neighbor-0.95 gate all switch on the
  flag; default path identical to before.
- Added 6 tests in `tests/test_router.py` (14 -> 20): 5 strict-path behaviors +
  1 `_env_flag` parser test.
- Added `tests/conftest.py` autouse fixture pinning `STRICT_ROUTING=False`, so
  an ambient `GATOWAY_STRICT_ROUTING` (providers calls `load_dotenv()`) can't
  flip routing mid-suite.

Port fidelity: `policy_eval.py:65` fetches via the same `router.fetch_neighbors`
(`NEIGHBORS_PER_MODEL=5`), so production strict sees the same evidence the
screened `strict_evidence` policy saw.

Verification: `404 passed, 28 skipped` (was 395+28; +6 of the +9 are this
change, +3 pre-date it). Suite still 404 with `GATOWAY_STRICT_ROUTING=true`
exported, proving the fixture holds. Env switch confirmed live: unset ->
floor 0.3; `=true` -> low-evidence routes to Kimi.

NOT landed: `gatoway/router.py` also carries a pre-existing uncommitted
`fetch_neighbors` extraction (part of the untracked policy-eval work), and the
whole tree sits on `docs/index-consolidation`. Landing cleanly = get the gate
(+ its 2 test files + this plan) onto a branch off `main` without dragging the
unrelated policy-eval work. Awaiting user's call on how to split/land.

## Gate — how to flip after validation

Still gated per the report's "no policy promoted". To promote:
1. Re-run `bank_density` + a fresh coding/open-ended eval (not the 16 holdout tasks).
2. If quality-safe, set `GATOWAY_STRICT_ROUTING=true` in the deploy env.
3. Watch routing mix (~90% Kimi expected) and cost (~9% over current).
Once settled, flip the default in code and delete the old branch — don't let
the two-rule fork linger.

Reverting the flag does NOT revert the data. `app.py` scores live decisions
into `decision_history`, the bank `decide()` reads from:
- A strict window leaves ~90% Kimi rows behind; after unsetting the flag the
  default router will see more Kimi evidence than before and promote to Kimi
  more often. Record the strict window's time range so those rows can be
  excluded on revert.
- Strict routing barely calls cheap models, so the bank won't accumulate the
  evidence needed to downgrade — densification must come from the offline
  pipeline, not live traffic.
- Unmeasured: `app.py`'s classifier-FAILURE path still routes to
  `FALLBACK_RUNG = gpt-oss` even under strict routing. The screening never
  exercised that path; leave it or decide separately.
