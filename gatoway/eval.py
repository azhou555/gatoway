"""Eval Harness (SPEC.md §8), the "budget-vs-quality tradeoff report" demo
artifact.

Runs a small hand-written, held-out benchmark suite (eval split -- never
written back to decision_history, see gatoway/batch_job.py) through two
paths:
    1. The router picks a model rung per task, then calls its provider.
    2. An "always highest-rung" baseline: every task goes to the last rung.

...then reports cost (sum of cost_cents) and effectiveness (per-task exact
match, fixture execution, Docker hidden tests, or rubric judge score)
for both,
and the headline cost-reduction / effectiveness-delta numbers.

Runs standalone: it does NOT require the FastAPI gateway (gatoway/app.py) to
be up. It talks to gatoway.router / gatoway.providers in-process.

Modes:
    --dry-run   Use canned response bands instead of calling litellm.
                No Docker required; code scores are scripted and judges heuristic.
                Auto-selected if NRP_API_KEY is not set in the
                environment (with a printed notice -- never silently
                guessed).
    (default)   Call real providers via gatoway.providers.call_provider().

The router tier decision itself prefers a real DB round-trip
(gatoway.router.classify() against the seeded decision_history bank, see
gatoway/seed.py) but degrades gracefully to a standalone approximation
(gatoway.router.approximate_rung() using the task's own difficulty label) if
Postgres isn't reachable, so this
harness never hard-depends on a live DB either.

Usage:
    python -m gatoway.eval
    python -m gatoway.eval --dry-run
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatoway.bank_corpus import TrainPrompt

from gatoway.coding_tasks import load_tasks, fenced_reference
from gatoway.rubrics import RUBRICS
from gatoway.providers import (
    MODEL_PARAMS_B,
    RUNG_NAMES,
    ProviderResponse,
    TIER_MODELS,
    call_provider,
)
from gatoway.router import DEFAULT_THRESHOLD, approximate_rung
from gatoway.session import compute_threshold

REPORT_PATH = Path(__file__).resolve().parent.parent / "docs" / "eval_report.md"

# Treat the eight benchmark tasks as one deliberately overlong simulated
# session. Threshold shifting begins on turn 4, so the report covers the
# min-max behavior that single-request evaluation previously skipped.
EVAL_EXPECTED_TURN_COUNT = 3
DEFAULT_EVAL_RUNS = 3
EVAL_PROVIDER_TIMEOUT_SECONDS = 120.0
EVAL_PROVIDER_ATTEMPTS = 2
EVAL_MAX_TOKENS = 512
EVAL_TEMPERATURE = 0.0

# --- Dry-run cost proxy: parameter count, not invented cents --------------
#
# --dry-run makes no real provider call, so there's no real cost_cents to
# read off a litellm response -- and NRP publishes no per-token prices for
# real runs either. Both paths therefore use the same cost proxy: each
# model's published parameter count (billions), from
# gatoway.providers.MODEL_PARAMS_B. See that table for the full rationale.


def param_count_b(tier: str) -> float:
    """Cost proxy for `tier`: its primary model's parameter count (billions)."""
    return MODEL_PARAMS_B[TIER_MODELS[tier][0]]


@dataclass
class BenchmarkTask:
    task_id: str
    prompt: str
    scoring_method: str  # "exact_match" | "python_execution" | "sql_execution" | "llm_judge"
    # exact_match: list of substrings that must ALL appear (case-insensitive)
    # llm_judge: list of keywords used by the length+keyword heuristic stub
    # execution scorers: unused; the task-specific fixture is pre-registered
    expected: list[str]
    # Hand-labeled difficulty (0-1), matching the difficulty bucket the task
    # was designed to exercise. Used only as the standalone-mode fallback
    # match when no DB is reachable (see module docstring).
    difficulty: float
    split: str = "eval"  # SPEC.md §8: eval split, never written back
    # Canned responses in three quality bands for --dry-run mode, hand-authored
    # to reflect a plausible gradient: cheap rungs do fine on easy tasks but
    # give thinner/partially-wrong answers on hard ones; the high band is
    # consistently thorough. This is what makes the dry-run report tell a
    # non-degenerate story (not "everything scores identically").
    canned_responses: dict[str, str] = field(default_factory=dict)
    suite: str = "original"
    rubric: list[str] = field(default_factory=list)
    task_dir: Path | None = None
    language: str = ""
    reference_response: str = ""
    expected_json: object = None
    category: str = ""


BENCHMARK_TASKS: list[BenchmarkTask] = [
    BenchmarkTask(
        task_id="capital_france",
        prompt="What is the capital of France?",
        scoring_method="exact_match",
        expected=["paris"],
        difficulty=0.10,
        canned_responses={
            "cheap": "The capital of France is Paris.",
            "medium": "Paris is the capital of France.",
            "frontier": "The capital of France is Paris.",
        },
    ),
    BenchmarkTask(
        task_id="arithmetic",
        prompt="What is 23 * 17?",
        scoring_method="exact_match",
        expected=["391"],
        difficulty=0.15,
        canned_responses={
            "cheap": "23 * 17 = 391.",
            "medium": "23 * 17 = 391.",
            "frontier": "23 * 17 = 391.",
        },
    ),
    BenchmarkTask(
        task_id="unit_conversion",
        prompt="Convert 68 degrees Fahrenheit to Celsius, rounded to the nearest integer.",
        scoring_method="exact_match",
        expected=["20"],
        difficulty=0.20,
        canned_responses={
            "cheap": "68F is 20C.",
            "medium": "68 degrees Fahrenheit is 20 degrees Celsius.",
            "frontier": "Using (F-32) * 5/9: (68-32) * 5/9 = 20 degrees Celsius.",
        },
    ),
    BenchmarkTask(
        task_id="quadratic_roots",
        prompt="Solve x^2 - 5x + 6 = 0 for x.",
        scoring_method="exact_match",
        expected=["2", "3"],
        difficulty=0.30,
        canned_responses={
            "cheap": "x = 2 or x = 3.",
            "medium": "Factoring gives (x-2)(x-3)=0, so x = 2 or x = 3.",
            "frontier": "Factoring: x^2 - 5x + 6 = (x-2)(x-3) = 0, so x = 2 and x = 3.",
        },
    ),
    BenchmarkTask(
        task_id="code_fix",
        prompt="Fix the off-by-one bug in: for i in range(1, n): print(arr[i])",
        scoring_method="python_execution",
        expected=[],
        difficulty=0.45,
        canned_responses={
            "cheap": "Try `for i in range(0, n-1): print(arr[i])` instead.",
            "medium": "Change it to `for i in range(0, n): print(arr[i])` -- "
                      "starting at 1 skips index 0, an off-by-one error.",
            "frontier": "The loop starts at 1, so index 0 is skipped -- a classic "
                        "off-by-one bug. Use `for i in range(0, n): print(arr[i])` "
                        "to cover every valid index from 0 to n-1.",
        },
    ),
    BenchmarkTask(
        task_id="sql_query",
        prompt="Write a SQL query to find the second-highest salary from an employees table.",
        scoring_method="sql_execution",
        expected=[],
        difficulty=0.50,
        canned_responses={
            "cheap": "SELECT MAX(salary) FROM employees;",
            "medium": "SELECT salary FROM employees ORDER BY salary DESC LIMIT 1 OFFSET 1;",
            "frontier": "SELECT DISTINCT salary FROM employees ORDER BY salary DESC "
                        "LIMIT 1 OFFSET 1; -- DISTINCT guards against duplicate top salaries.",
        },
    ),
    BenchmarkTask(
        task_id="multistep_planning",
        prompt="Plan a 3-step migration strategy to move a monolithic app to "
               "microservices, considering data consistency risks.",
        scoring_method="llm_judge",
        expected=["strangler", "data consistency", "rollback", "incremental"],
        difficulty=0.75,
        canned_responses={
            "cheap": "Split the app into services and move the data over.",
            "medium": "1) Extract one bounded context at a time. 2) Keep the "
                      "shared DB temporarily. 3) Cut over once stable.",
            "frontier": "1) Extract a bounded context behind a strangler-fig facade, "
                        "keeping the shared DB short-term for data consistency. "
                        "2) Introduce an outbox pattern for incremental, dual-write-safe "
                        "migration of that context's data. 3) Cut over to its own store "
                        "with a rollback plan and shadow traffic before full cutover.",
        },
    ),
    BenchmarkTask(
        task_id="hard_math_proof",
        prompt="Prove that the square root of 2 is irrational.",
        scoring_method="llm_judge",
        expected=["contradiction", "even", "odd", "irrational"],
        difficulty=0.85,
        canned_responses={
            "cheap": "sqrt(2) is irrational because it cannot be written as a fraction.",
            "medium": "Assume sqrt(2)=a/b in lowest terms; then a^2=2b^2 so a is even; "
                      "this leads to b also being even, a contradiction.",
            "frontier": "Assume for contradiction sqrt(2)=a/b in lowest terms. Then "
                        "a^2=2b^2, so a^2 is even, so a is even; write a=2k, giving "
                        "4k^2=2b^2 so b^2=2k^2, so b is even too -- contradicting that "
                        "a/b was in lowest terms. Hence sqrt(2) is irrational.",
        },
    ),
]


for _task in BENCHMARK_TASKS:
    _task.rubric = RUBRICS.get(_task.task_id, [])
    _task.reference_response = _task.canned_responses["frontier"]

for _artifact in load_tasks("eval"):
    _reference = fenced_reference(_artifact)
    _low = ("No detailed proposal." if _artifact.language == "design" else
            chr(96) * 3 + _artifact.language + "\n// incomplete answer\n" + chr(96) * 3)
    BENCHMARK_TASKS.append(BenchmarkTask(
        task_id=_artifact.task_id, prompt=_artifact.prompt,
        scoring_method="llm_judge" if _artifact.language == "design" else "code_tests",
        expected=[], difficulty=_artifact.difficulty,
        canned_responses={"cheap": _low, "medium": _reference, "frontier": _reference},
        suite="coding", rubric=_artifact.rubric, task_dir=_artifact.directory,
        language=_artifact.language, reference_response=_reference,
    ))


def benchmark_tasks(suite: str = "legacy") -> list[BenchmarkTask]:
    """Keep the historical suite stable; breadth is an explicit new baseline."""
    if suite == "legacy":
        return list(BENCHMARK_TASKS)
    if suite != "expanded":
        raise ValueError(f"unknown suite: {suite}")
    import json
    from gatoway.breadth_tasks import load_cases
    additions = []
    for case in load_cases():
        reference = json.dumps(case["answer"], ensure_ascii=False)
        additions.append(BenchmarkTask(
            task_id=case["task_id"], prompt=case["prompt"], scoring_method="json_exact",
            expected=[], expected_json=case["answer"], difficulty=case["difficulty"],
            suite=case["suite"], category=case["category"], reference_response=reference,
            canned_responses={band: reference for band in ("cheap", "medium", "frontier")},
        ))
    return [*BENCHMARK_TASKS, *additions]


def score_exact_match(response: str, expected: list[str]) -> float:
    """1.0 if every required substring appears in the response (case-insensitive),
    else 0.0. Deliberately binary -- this is the pass/fail branch of SPEC.md §8's
    "exact-match / execution-based pass-fail" scoring.
    """
    lowered = response.lower().replace("−", "-")
    return 1.0 if all(term.lower().replace("−", "-") in lowered for term in expected) else 0.0


# --- Execution-based scorers ----------------------------------------------

_FENCED_BLOCK_RE = re.compile(
    r"```(?P<language>[a-zA-Z0-9_+-]*)\s*\n?(?P<body>.*?)```", re.DOTALL
)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _python_candidates(response: str) -> list[str]:
    """Extract likely Python snippets from a prose or Markdown response."""
    candidates = [
        match.group("body").strip()
        for match in _FENCED_BLOCK_RE.finditer(response)
        if match.group("language").lower() in ("", "py", "python")
    ]
    candidates.extend(
        snippet.strip()
        for snippet in _INLINE_CODE_RE.findall(response)
        if "for " in snippet
    )
    candidates.extend(
        line[line.find("for "):].strip()
        for line in response.splitlines()
        if "for " in line
    )
    candidates.append(response.strip())
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


_ALLOWED_PYTHON_NODES = (
    ast.Module,
    ast.For,
    ast.Expr,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.Subscript,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Tuple,
    ast.List,
)
_ALLOWED_PYTHON_CALLS = {"print", "range", "len", "enumerate"}
_PYTHON_FIXTURE_NAMES = _ALLOWED_PYTHON_CALLS | {"arr", "n"}


def _safe_python_tree(candidate: str) -> ast.Module | None:
    """Parse the tiny loop answer while rejecting general-purpose code.

    Model output is untrusted. The benchmark only needs a single finite loop,
    so imports, attributes, definitions, comprehensions and arbitrary calls
    are deliberately outside the accepted language.
    """
    try:
        tree = ast.parse(candidate)
    except SyntaxError:
        return None

    nodes = list(ast.walk(tree))
    loops = [node for node in nodes if isinstance(node, ast.For)]
    if len(loops) != 1:
        return None
    if any(not isinstance(node, _ALLOWED_PYTHON_NODES) for node in nodes):
        return None

    target_names = {
        node.id
        for node in ast.walk(loops[0].target)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    allowed_names = _PYTHON_FIXTURE_NAMES | target_names
    for node in nodes:
        if isinstance(node, ast.Name) and node.id not in allowed_names:
            return None
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_PYTHON_CALLS:
                return None
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            if abs(node.value) > 10_000:
                return None
    return tree


def score_python_execution(
    response: str,
    fixtures: tuple[tuple[list[int], list[tuple[object, ...]]], ...] | None = None,
) -> float:
    """Execute a constrained loop against trusted input/output fixtures."""
    if re.search(
        r"^\s*(?:from\s+\S+\s+import|import|while|def|class)\b",
        response,
        re.MULTILINE,
    ):
        return 0.0

    if fixtures is None:
        fixtures = tuple(
            (values, [(value,) for value in values])
            for values in ([10, 20, 30], [7], [])
        )
    if not fixtures:
        raise ValueError("execution scoring requires at least one fixture")
    for candidate in _python_candidates(response):
        tree = _safe_python_tree(candidate)
        if tree is None:
            continue

        passed = True
        for values, expected_output in fixtures:
            printed: list[tuple[object, ...]] = []

            def capture_print(*args, **kwargs):
                if kwargs:
                    raise ValueError("print keyword arguments are not supported")
                printed.append(args)

            namespace = {
                "arr": list(values),
                "n": len(values),
                "print": capture_print,
                "range": range,
                "len": len,
                "enumerate": enumerate,
            }
            try:
                exec(compile(tree, "<benchmark-answer>", "exec"), {"__builtins__": {}}, namespace)
            except Exception:  # A candidate that does not run simply fails the fixture.
                passed = False
                break
            if printed != expected_output:
                passed = False
                break
        if passed:
            return 1.0
    return 0.0


def _sql_candidates(response: str) -> list[str]:
    """Extract likely SELECT statements from a prose or Markdown response."""
    candidates = [
        match.group("body").strip()
        for match in _FENCED_BLOCK_RE.finditer(response)
        if match.group("language").lower() in ("", "sql")
    ]
    candidates.extend(
        snippet.strip()
        for snippet in _INLINE_CODE_RE.findall(response)
        if re.match(r"\s*(SELECT|WITH)\b", snippet, re.IGNORECASE)
    )
    match = re.search(r"\b(SELECT|WITH)\b", response, re.IGNORECASE)
    if match:
        suffix = response[match.start():].strip()
        candidates.append(suffix.split(";", 1)[0].strip())
    candidates.append(response.strip())
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _run_salary_query(query: str, salaries: list[int]) -> list[tuple[object, ...]] | None:
    if not re.match(r"\s*(SELECT|WITH)\b", query, re.IGNORECASE):
        return None

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, salary INTEGER)"
        )
        connection.executemany(
            "INSERT INTO employees (name, salary) VALUES (?, ?)",
            [(f"employee-{index}", salary) for index, salary in enumerate(salaries)],
        )

        allowed_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ}
        allowed_functions = {"max", "dense_rank", "row_number"}

        def authorize(action, _arg1, arg2, _database, _trigger):
            if action == sqlite3.SQLITE_FUNCTION:
                return (
                    sqlite3.SQLITE_OK
                    if arg2 and arg2.lower() in allowed_functions
                    else sqlite3.SQLITE_DENY
                )
            return sqlite3.SQLITE_OK if action in allowed_actions else sqlite3.SQLITE_DENY

        connection.set_authorizer(authorize)
        connection.set_progress_handler(lambda: 1, 100_000)
        return connection.execute(query).fetchall()
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def score_sql_execution(
    response: str,
    fixtures: tuple[tuple[list[int], list[tuple[object, ...]]], ...] | None = None,
) -> float:
    """Run a read-only query against trusted salary/result fixtures."""
    if fixtures is None:
        fixtures = (
            ([100, 100, 90, 80], [(90,)]),
            ([50, 40, 40, 30], [(40,)]),
            ([7, 3], [(3,)]),
        )
    if not fixtures:
        raise ValueError("execution scoring requires at least one fixture")
    for candidate in _sql_candidates(response):
        if all(
            _run_salary_query(candidate, salaries) == expected
            for salaries, expected in fixtures
        ):
            return 1.0
    return 0.0


# --- llm_judge stub --------------------------------------------------------
#
# Dry runs alone use this heuristic stand-in. Live scoring uses judge.py.
# Half the score
# comes from response length relative to a target (a proxy for "did it
# actually explain itself" vs a one-liner), half from how many of the task's
# pre-registered keywords showed up (a proxy for "did it cover the right
# concepts"). Scripted scores do not measure live answer correctness.
LLM_JUDGE_TARGET_LENGTH_CHARS = 220


def score_llm_judge_stub(response: str, keywords: list[str]) -> float:
    length_component = min(len(response) / LLM_JUDGE_TARGET_LENGTH_CHARS, 1.0)
    lowered = response.lower()
    if keywords:
        keyword_component = sum(1 for kw in keywords if kw.lower() in lowered) / len(keywords)
    else:
        keyword_component = 0.0
    return 0.5 * length_component + 0.5 * keyword_component


def score_task(task: BenchmarkTask | TrainPrompt, response_text: str, *, dry_run: bool = False) -> float:
    if task.scoring_method == "json_exact":
        from gatoway.breadth_tasks import score_json
        return score_json(response_text, task.expected_json)
    if task.scoring_method == "exact_match":
        return score_exact_match(response_text, task.expected)
    if task.scoring_method == "python_execution":
        return score_python_execution(response_text, getattr(task, "execution_fixtures", None))
    if task.scoring_method == "sql_execution":
        return score_sql_execution(response_text, getattr(task, "execution_fixtures", None))
    if task.scoring_method == "llm_judge":
        if not dry_run:
            raise ValueError("live rubric scoring requires await bank_corpus.score")
        return score_llm_judge_stub(response_text, task.expected)
    raise ValueError(f"unknown scoring_method {task.scoring_method!r}")


async def _dry_run_provider(tier: str, task: BenchmarkTask) -> ProviderResponse:
    rung_index = RUNG_NAMES.index(tier)
    if rung_index <= 1:
        response_band = "cheap"
    elif rung_index <= 4:
        response_band = "medium"
    else:
        response_band = "frontier"
    content = task.canned_responses.get(response_band, "")
    return ProviderResponse(
        content=content,
        model_id=f"dry-run/{tier}",
        input_tokens=0,
        output_tokens=0,
        cost_cents=param_count_b(tier),  # cost proxy in --dry-run: see module docstring above
        raw=None,
    )


async def _real_provider(tier: str, task: BenchmarkTask) -> ProviderResponse:
    model = TIER_MODELS[tier][0]
    for attempt in range(1, EVAL_PROVIDER_ATTEMPTS + 1):
        try:
            return await asyncio.wait_for(
                call_provider(
                    model,
                    [{"role": "user", "content": task.prompt}],
                    temperature=EVAL_TEMPERATURE,
                    max_tokens=2048 if task.suite == "coding" else EVAL_MAX_TOKENS,
                ),
                timeout=EVAL_PROVIDER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            if attempt == EVAL_PROVIDER_ATTEMPTS:
                raise
            print(
                f"  [warn] {model} timed out for {task.task_id}; retrying once",
                flush=True,
            )
    raise AssertionError("unreachable")


async def pick_router_tier(
    task: BenchmarkTask, pool, current_threshold: float = DEFAULT_THRESHOLD, *, require_db=False
) -> str:
    """Route `task` through the real router when a DB is available, else
    fall back to a standalone approximation. See module docstring.
    """
    if pool is not None:
        try:
            from gatoway.router import classify

            decision = await classify(task.prompt, pool, current_threshold)
            return decision.tier
        except Exception as exc:  # DB reachable at connect time but query failed, etc.
            if require_db:
                raise
            print(f"  [warn] classify() failed for {task.task_id!r} ({exc}); "
                  f"falling back to standalone difficulty-based routing")

    # Standalone fallback: no DB, or classify() failed. This approximation is
    # eval-only; production always selects from per-model outcome evidence.
    if require_db:
        raise RuntimeError("DB-backed evaluation requires a working database")
    return approximate_rung(task.difficulty, current_threshold)


@dataclass
class TaskResult:
    task_id: str
    tier: str
    cost_cents: float
    score: float
    current_threshold: float
    suite: str = "original"


@dataclass
class EvalRun:
    router_results: list[TaskResult]
    baseline_results: list[TaskResult]


async def run_eval(dry_run: bool, pool, *, require_db=False, tasks=None) -> tuple[list[TaskResult], list[TaskResult]]:
    """Run the original and coding suites as independent simulated sessions."""
    from gatoway.bank_corpus import score
    from gatoway.code_grader import CodeGrader
    grader = CodeGrader()
    provider_fn = _dry_run_provider if dry_run else _real_provider

    router_results: list[TaskResult] = []
    baseline_results: list[TaskResult] = []

    turn_counts: dict[str, int] = {}
    for task in (BENCHMARK_TASKS if tasks is None else tasks):
        turn_counts[task.suite] = turn_counts.get(task.suite, 0) + 1
        turn_number = turn_counts[task.suite]
        current_threshold = compute_threshold(
            turn_count=turn_number,
            expected_turn_count=EVAL_EXPECTED_TURN_COUNT,
        )
        router_tier = await pick_router_tier(task, pool, current_threshold, require_db=require_db)
        print(
            f"  [{task.suite} turn {turn_number}/8] {task.task_id}: "
            f"threshold={current_threshold:.2f}, router={router_tier}",
            flush=True,
        )
        router_response = await provider_fn(router_tier, task)
        router_results.append(TaskResult(
            task_id=task.task_id,
            tier=router_tier,
            cost_cents=router_response.cost_cents,
            score=await score(task, router_response.content, router_response.model_id,
                              dry_run=dry_run, grader=grader),
            suite=task.suite,
            current_threshold=current_threshold,
        ))

        baseline_tier = RUNG_NAMES[-1]
        baseline_response = await provider_fn(baseline_tier, task)
        baseline_results.append(TaskResult(
            task_id=task.task_id,
            tier=baseline_tier,
            cost_cents=baseline_response.cost_cents,
            score=await score(task, baseline_response.content, baseline_response.model_id,
                              dry_run=dry_run, grader=grader),
            suite=task.suite,
            current_threshold=current_threshold,
        ))

    return router_results, baseline_results


async def run_eval_repeated(dry_run: bool, pool, runs: int, *, require_db=False, checkpoint: Path | None = None, tasks=None) -> list[EvalRun]:
    """Run the same held-out session repeatedly for stability measurement."""
    if runs < 1:
        raise ValueError("runs must be at least 1")

    results: list[EvalRun] = []
    for run_number in range(1, runs + 1):
        print(f"[run {run_number}/{runs}] starting simulated session", flush=True)
        router_results, baseline_results = await run_eval(dry_run, pool, require_db=require_db, tasks=tasks)
        results.append(EvalRun(router_results, baseline_results))
        if checkpoint:
            from dataclasses import asdict
            import json
            from gatoway.judge import JUDGE_VERSION
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps({
                "dry_run": dry_run, "require_db": require_db,
                "task_ids": [task.task_id for task in (BENCHMARK_TASKS if tasks is None else tasks)],
                "judge_version": JUDGE_VERSION,
                "runs": [asdict(run) for run in results],
            }, indent=2) + "\n")
    return results


def _pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator * 100


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _mean_range(
    values: list[float],
    fmt,
    always_range: bool = False,
    range_separator: str = "–",
) -> str:
    mean = fmt(_mean(values))
    low = fmt(min(values))
    high = fmt(max(values))
    if not always_range and low == high:
        return mean
    return f"{mean} ({low}{range_separator}{high})"


def _results_by_task(runs: list[EvalRun], side: str, tasks=None) -> dict[str, list[TaskResult]]:
    grouped = {task.task_id: [] for task in (BENCHMARK_TASKS if tasks is None else tasks)}
    for run in runs:
        results = run.router_results if side == "router" else run.baseline_results
        for result in results:
            grouped[result.task_id].append(result)
    return grouped


def stability_gate(runs: list[EvalRun], tasks=None) -> tuple[bool, str]:
    """Require stable binary scores for every checkable task over 3+ runs."""
    if len(runs) < 3:
        return False, f"not evaluated: {len(runs)}/3 required runs"

    tasks = BENCHMARK_TASKS if tasks is None else tasks
    checkable = {
        task.task_id
        for task in tasks
        if task.scoring_method in {"exact_match", "python_execution", "sql_execution", "code_tests", "json_exact"}
    }
    unstable: list[str] = []
    for side in ("router", "baseline"):
        grouped = _results_by_task(runs, side, tasks)
        for task_id in checkable:
            task = next(task for task in tasks if task.task_id == task_id)
            results = grouped[task_id]
            scores = {float(result.score == 1.0) if task.scoring_method == "code_tests"
                      else result.score for result in results}
            if len(results) != len(runs) or len(scores) != 1:
                unstable.append(f"{side}/{task_id}")

    if unstable:
        return False, "unstable scores: " + ", ".join(sorted(unstable))
    return True, f"all {len(checkable)} checkable tasks had stable pass/fail outcomes"


def build_report(
    runs: list[EvalRun],
    dry_run: bool,
    db_backed: bool | None = None,
    bank_rows: int | None = None,
    tasks=None,
) -> str:
    """Build a session-level report with per-task means and ranges."""
    if not runs:
        raise ValueError("at least one eval run is required")
    tasks = BENCHMARK_TASKS if tasks is None else tasks

    router_costs = [sum(result.cost_cents for result in run.router_results) for run in runs]
    baseline_costs = [sum(result.cost_cents for result in run.baseline_results) for run in runs]
    router_effectiveness = [
        _mean([result.score for result in run.router_results]) for run in runs
    ]
    baseline_effectiveness = [
        _mean([result.score for result in run.baseline_results]) for run in runs
    ]
    cost_reductions = [
        _pct(baseline - router, baseline)
        for router, baseline in zip(router_costs, baseline_costs)
    ]
    effectiveness_deltas = [
        (router - baseline) * 100
        for router, baseline in zip(router_effectiveness, baseline_effectiveness)
    ]

    # Neither mode has a real currency figure: NRP publishes no per-token
    # prices, so cost is a parameter-count proxy either way (see
    # param_count_b() above). Be explicit rather than imply real dollars.
    cost_label = "Compute Proxy (B params)" if dry_run else "Cost Proxy (arbitrary units)"
    cost_word = "compute-proxy" if dry_run else "cost-proxy"
    cost_fmt = "{:.1f}".format if dry_run else "{:.3f}".format
    score_fmt = "{:.2f}".format
    pct_fmt = "{:.1f}%".format

    router_by_task = _results_by_task(runs, "router", tasks)
    baseline_by_task = _results_by_task(runs, "baseline", tasks)
    gate_passed, gate_detail = stability_gate(runs, tasks)
    effectiveness_delta_summary = _mean_range(
        effectiveness_deltas,
        lambda value: f"{value:+.1f} pt",
        always_range=True,
        range_separator=" to ",
    )

    lines = []
    lines.append("# Eval Report: Router vs Always-Highest-Rung Baseline\n")
    lines.append(
        ("_--dry-run: no real provider calls; scores come from canned response bands._ "
         if dry_run else
         "_Real calls against NRP-hosted models._ ")
        + "_Cost is a parameter-count proxy, not real spend: NRP has no per-token "
          "billing, so each model is priced at its published parameter count in "
          "billions per 1M tokens. Only relative ordering is meaningful._\n"
    )
    lines.append(
        "_Scoring: exact match for factual tasks; constrained Python/SQLite "
        "fixtures for legacy tasks; "
        + ("scripted coding scores and heuristic judging in dry-run. No containers run._\n"
           if dry_run else
           "Docker execution for all Python/TypeScript answers; rubric LLM judging "
           "for all open-ended tasks (judge overhead excluded from answer cost)._\n")
    )
    sessions = "two" if len(tasks) == 16 else "four" if len(tasks) == 32 else str(len({t.suite for t in tasks}))
    lines.append(
        f"_Session evaluation: {sessions} independent eight-turn sessions per run; "
        f"expected turn count {EVAL_EXPECTED_TURN_COUNT}; thresholds therefore "
        "rise on later turns._\n"
    )
    from gatoway.judge import JUDGE_VERSION
    lines.append(f"_Judge version: {JUDGE_VERSION}. Strict whole-response JSON equality grades the breadth tasks._\n")
    if any(task.scoring_method == "json_exact" for task in tasks):
        lines.append("Breadth tasks are held-out generalization challenges; the historical training bank "
                     "has not been expanded to cover them. Report their quality separately from the original suites.\n")
    if db_backed is not None:
        if db_backed:
            bank_detail = f" ({bank_rows} rows)" if bank_rows is not None else ""
            lines.append(
                f"_Routing: DB-backed pgvector `decision_history` lookup{bank_detail}._\n"
            )
        else:
            lines.append(
                "_Routing: standalone difficulty-label approximation; no database used._\n"
            )
    if not dry_run:
        lines.append(
            f"_Generation controls: temperature {EVAL_TEMPERATURE:g}, "
            f"maximum {EVAL_MAX_TOKENS} tokens for original tasks / 2048 for coding, {EVAL_PROVIDER_TIMEOUT_SECONDS:g}s "
            f"timeout, {EVAL_PROVIDER_ATTEMPTS - 1} timeout retry._\n"
        )
    lines.append(
        f"**Headline across {len(runs)} runs: "
        f"{_mean_range(cost_reductions, pct_fmt, always_range=True)} {cost_word} "
        "reduction, "
        f"{effectiveness_delta_summary} "
        "effectiveness delta vs always-highest-rung.**\n"
    )
    lines.append("Expanded suite: a new baseline; not comparable to historical eight-task gates.\n")
    lines.append(f"**Stability gate: {'PASS' if gate_passed else 'FAIL'}** — {gate_detail}.\n")
    lines.append(
        f"| Suite/Turn | Task | Threshold | Router Tier(s) | Router {cost_label} mean (range) | "
        f"Router Score mean (range) | Baseline {cost_label} mean (range) | "
        "Baseline Score mean (range) |"
    )
    lines.append("|---:|---|---:|---|---:|---:|---:|---:|")
    turns: dict[str, int] = {}
    for task in tasks:
        turns[task.suite] = turns.get(task.suite, 0) + 1
        turn_number = turns[task.suite]
        router_results = router_by_task[task.task_id]
        baseline_results = baseline_by_task[task.task_id]
        tiers = " / ".join(dict.fromkeys(result.tier for result in router_results))
        always_range = task.scoring_method == "llm_judge"
        lines.append(
            f"| {task.suite}/{turn_number} | {task.task_id} | "
            f"{router_results[0].current_threshold:.2f} | {tiers} | "
            f"{_mean_range([r.cost_cents for r in router_results], cost_fmt)} | "
            f"{_mean_range([r.score for r in router_results], score_fmt, always_range)} | "
            f"{_mean_range([r.cost_cents for r in baseline_results], cost_fmt)} | "
            f"{_mean_range([r.score for r in baseline_results], score_fmt, always_range)} |"
        )
    lines.append("")
    lines.append(
        f"**Session totals (mean and range)** — Router: "
        f"{_mean_range(router_costs, cost_fmt, always_range=True)}, "
        f"{_mean_range([value * 100 for value in router_effectiveness], pct_fmt, always_range=True)} "
        f"effective. Highest-rung baseline: "
        f"{_mean_range(baseline_costs, cost_fmt, always_range=True)}, "
        f"{_mean_range([value * 100 for value in baseline_effectiveness], pct_fmt, always_range=True)} "
        "effective."
    )
    lines.append("\n## Per-suite results\n")
    lines.append("| Suite | Router effectiveness | Baseline effectiveness | Cost reduction |")
    lines.append("|---|---:|---:|---:|")
    for suite in dict.fromkeys(task.suite for task in tasks):
        router = [[r for r in run.router_results if r.suite == suite] for run in runs]
        baseline = [[r for r in run.baseline_results if r.suite == suite] for run in runs]
        reductions = [_pct(sum(b.cost_cents for b in bs) - sum(r.cost_cents for r in rs),
                           sum(b.cost_cents for b in bs)) for rs, bs in zip(router, baseline)]
        lines.append(
            f"| {suite} | "
            f"{_mean_range([_mean([r.score for r in rs])*100 for rs in router], pct_fmt)} | "
            f"{_mean_range([_mean([r.score for r in bs])*100 for bs in baseline], pct_fmt)} | "
            f"{_mean_range(reductions, pct_fmt)} |"
        )
    return "\n".join(lines)


async def _try_get_pool():
    try:
        from gatoway.db import get_pool

        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        return pool
    except Exception as exc:
        print(f"[info] Postgres unavailable ({exc}); running eval in standalone mode "
              f"(router rung decisions approximated from task difficulty labels, "
              f"no decision_history lookups).")
        return None


async def _main(dry_run: bool, runs: int, *, require_db=False, database=None, checkpoint=None,
                suite="legacy", report=None) -> None:
    tasks = benchmark_tasks(suite)
    report_path = report or (REPORT_PATH if suite == "legacy" else REPORT_PATH.with_name("eval_report_expanded.md"))
    if database:
        from gatoway.bootstrap_bank import isolated_pool
        pool = await isolated_pool(database)
        require_db = True
    else:
        pool = await _try_get_pool()
    if require_db and pool is None:
        raise RuntimeError("DB-backed evaluation requires a working database")
    bank_rows = (
        await pool.fetchval("SELECT count(*) FROM decision_history")
        if pool is not None
        else None
    )
    try:
        eval_runs = await run_eval_repeated(dry_run, pool, runs, require_db=require_db, checkpoint=checkpoint, tasks=tasks)
    finally:
        if pool is not None:
            from gatoway.db import close_pool

            if database:
                await pool.close()
            else:
                await close_pool()

    report = build_report(
        eval_runs,
        dry_run,
        db_backed=pool is not None,
        bank_rows=bank_rows,
        tasks=tasks,
    )
    print(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report + "\n")
    print(f"\n[info] Wrote report to {report_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gatoway eval harness")
    parser.add_argument("--dry-run", action="store_true",
                         help="Use canned responses instead of calling real providers.")
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_EVAL_RUNS,
        help=f"Repeated sessions to aggregate (default: {DEFAULT_EVAL_RUNS}).",
    )
    parser.add_argument("--require-db", action="store_true",
                        help="Fail rather than approximate routing if the database fails.")
    parser.add_argument("--database", help="Use a marked isolated gatoway_eval_ database.")
    parser.add_argument("--checkpoint", type=Path, help="Record structured per-run results.")
    parser.add_argument("--suite", choices=("legacy", "expanded"), default="legacy",
                        help="Original 16 tasks, or 32 including objective breadth tasks.")
    parser.add_argument("--report", type=Path, help="Write to a separate report path.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    dry_run = args.dry_run
    if not dry_run and not os.environ.get("NRP_API_KEY"):
        if args.require_db or args.database:
            raise SystemExit("Live DB-backed gate requires NRP_API_KEY")
        print("[info] No NRP_API_KEY set -- auto-falling back to --dry-run.")
        dry_run = True
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    asyncio.run(_main(dry_run, args.runs, require_db=args.require_db,
                      database=args.database, checkpoint=args.checkpoint,
                      suite=args.suite, report=args.report))
