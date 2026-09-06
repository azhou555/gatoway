# Agentic Coding Benchmark

## Purpose

The original Gatoway evaluation sends independent prompts and scores one
response. That measures routing for chat-shaped work, but it does not answer
whether a routed model can change a repository, survive executable grading,
use failure feedback, and finish a multi-turn task.

`gatoway.agentic_eval` adds that missing layer without mixing it into the
lightweight router-vs-frontier report. Its conventions are intentionally close
to established coding-agent benchmarks:

- [SWE-bench](https://github.com/SWE-bench/SWE-bench) evaluates patches for
  real GitHub issues in reproducible Docker environments.
- [Terminal-Bench / Harbor](https://github.com/harbor-framework/terminal-bench)
  packages tasks with an environment, tests, and an oracle solution and checks
  task stability by repeating oracle runs.
- [SWE-Lancer](https://openai.com/index/swe-lancer/) grades real software work
  with end-to-end tests in unified Docker environments.
- The [OpenHands evaluation harness](https://docs.openhands.dev/openhands/usage/developers/evaluation-harness)
  models an agent as a bounded loop of actions and environment observations.

## What the harness does

For every task and every run:

1. Copy the starter repository and grader tests into a fresh temporary
   workspace. The model prompt contains the issue and editable source files,
   but not the tests or oracle.
2. Route the issue through the normal Gatoway classifier. If PostgreSQL is not
   available, use the task's held-out difficulty label through the same pure
   decision function.
3. Ask the selected NRP model for one unified diff.
4. Reject patches that traverse directories, edit tests, create/delete files,
   rename paths, change modes, or touch anything outside the declared editable
   source set. Apply accepted patches with `git apply`.
5. Run the held-out standard-library test suite inside Docker with no network,
   a read-only filesystem and bind mount, dropped capabilities, no privilege
   escalation, and CPU/memory/PID/time limits. The preflight resolves the image
   tag to an immutable image ID, uses that ID for every task, and records it in
   the report.
6. On failure, append the model response, execution observation, and current
   source snapshot to the conversation. Route and attempt another repair, up
   to the task's turn limit.

The session threshold uses an expected length of one turn. A repair therefore
raises the threshold from `0.50` to `0.90`, allowing the current tier router to
promote a borderline task after an unsuccessful attempt. The report records
the exact tier path so this behavior is observable rather than inferred.

## Initial task set

| Task | Difficulty | Main failure mode | Held-out checks |
|---|---:|---|---|
| `ttl_cache` | 0.58 | boundary semantics and falsey cached values | expiration, eviction, disabled cache, loader calls |
| `dependency_planner` | 0.68 | cross-record planning and validation | stable topology, missing dependencies, cycles, duplicates, mutation |
| `webhook_idempotency` | 0.82 | retry and concurrency correctness | sequential/concurrent deduplication, failure retry, per-key parallelism |

Each fixture under `benchmarks/agentic/<task>/` contains:

- `task.toml`: ID, held-out difficulty, and maximum turns;
- `task.md`: issue text shown to the model;
- `repo/`: starter repository shown to the model and copied per run;
- `grader_tests/`: tests copied into the grader workspace but omitted from the
  prompt;
- `oracle.patch`: repository-owned solution used only by `--dry-run` and unit
  tests to prove the task and grader are internally consistent.

## Metrics and commands

The generated report includes task solve rate, first-pass solve rate, mean
turns, tier switches, per-task tier and concrete-model paths, token usage,
provider latency, and aggregate compute/cost proxy. The production-readiness
gate requires three runs, every task passing at least two of three times, and
no attempt exhausting both models configured for its tier.

```bash
docker pull python:3.13-slim
python -m gatoway.agentic_eval --dry-run
python -m gatoway.agentic_eval --runs 3
```

The dry run deliberately fails patch parsing on turn one and uses the oracle
on turn two. It is a deterministic test of isolation, patching, observation
chaining, threshold movement, and execution scoring. It is not evidence about
model quality. Live NRP runs are the quality measurement.

## Interpretation boundary

This is a deliberately small agentic readiness gate, not a replacement for
SWE-bench Verified or Terminal-Bench:

- Three synthetic Python tasks do not represent large, dependency-heavy real
  repositories and may not predict broad production performance.
- The model emits patches from repository snapshots; it does not yet receive a
  shell, search, editor, or arbitrary tool API. The loop tests iterative
  repair, not a full autonomous terminal agent.
- Docker hardening reduces accidental host impact, but this is a local
  benchmark sandbox, not a hostile multi-tenant execution service.
- Parameter count remains a compute proxy because NRP publishes no per-token
  prices. A proxy-cost win is not a dollar-cost claim.
- Timed-out provider calls do not return usage metadata. Their full wall time is
  included in provider latency, but they add no tokens or compute proxy, so
  those two totals are conservative when timeouts occur.
- A useful production result should use at least three live runs and report
  failures and variance, not only the best run.

The next scale step is an adapter that points an external SWE-bench/Harbor
agent runner at Gatoway's OpenAI-compatible endpoint. Before treating that as
a gateway result, the API must preserve any tool-call fields the chosen agent
harness requires; the current miniature suite avoids claiming that capability.
