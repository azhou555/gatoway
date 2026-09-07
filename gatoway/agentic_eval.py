"""Isolated, multi-turn coding evaluation for Gatoway.

Unlike ``gatoway.eval``, this harness gives a model a small repository, applies
its unified diff, executes held-out tests, and returns the failure observation
for another routed turn. Generated code is graded inside a locked-down Docker
container; the host checkout is never modified.

Usage:
    docker pull python:3.13-slim
    python -m gatoway.agentic_eval --dry-run
    python -m gatoway.agentic_eval
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from gatoway.eval import param_count_b
from gatoway.providers import TIER_MODELS, call_provider
from gatoway.router import DEFAULT_THRESHOLD, TIERS, decide
from gatoway.session import compute_threshold

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "agentic"
REPORT_PATH = PROJECT_ROOT / "docs" / "agentic_eval_report.md"
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "agentic_eval"

AGENTIC_EXPECTED_TURNS = 1
PROVIDER_TIMEOUT_SECONDS = 120.0
PROVIDER_MAX_TOKENS = 2400
MAX_OBSERVATION_CHARS = 6000
DEFAULT_DOCKER_IMAGE = "python:3.13-slim"


class AgenticInfrastructureError(RuntimeError):
    """The evaluator itself could not run, so the model must not be scored."""


@dataclass(frozen=True)
class AgenticTask:
    task_id: str
    root: Path
    issue: str
    difficulty: float
    max_turns: int
    editable_files: tuple[str, ...]

    @property
    def oracle_patch(self) -> str:
        return (self.root / "oracle.patch").read_text()


@dataclass(frozen=True)
class AgentResponse:
    content: str
    model_id: str
    cost_cents: float
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0
    provider_error: str | None = None
    finish_reason: str | None = None
    provider_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatchResult:
    applied: bool
    observation: str


@dataclass(frozen=True)
class GradeResult:
    passed: bool
    output: str
    infrastructure_error: bool = False


@dataclass(frozen=True)
class AgenticAttempt:
    turn: int
    threshold: float
    tier: str
    model_id: str
    cost_cents: float
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    patch_applied: bool
    tests_passed: bool
    observation: str = field(repr=False)
    router_tier: str = ""
    minimum_tier: str = ""
    finish_reason: str | None = None
    provider_failures: tuple[str, ...] = ()
    messages_sent: tuple[dict[str, str], ...] = field(default=(), repr=False)
    response_text: str = field(default="", repr=False)


@dataclass(frozen=True)
class AgenticResult:
    task_id: str
    passed: bool
    attempts: tuple[AgenticAttempt, ...]
    evaluation_path: str = "router"

    @property
    def total_cost_cents(self) -> float:
        return sum(attempt.cost_cents for attempt in self.attempts)

    @property
    def tiers(self) -> tuple[str, ...]:
        return tuple(attempt.tier for attempt in self.attempts)

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(attempt.model_id.removeprefix("openai/") for attempt in self.attempts)

    @property
    def tier_switches(self) -> int:
        return sum(left != right for left, right in zip(self.tiers, self.tiers[1:]))

    @property
    def total_tokens(self) -> int:
        return sum(
            attempt.input_tokens + attempt.output_tokens for attempt in self.attempts
        )

    @property
    def provider_latency_seconds(self) -> float:
        return sum(attempt.latency_seconds for attempt in self.attempts)


@dataclass(frozen=True)
class AgenticEvalRun:
    router_results: tuple[AgenticResult, ...]
    baseline_results: tuple[AgenticResult, ...] = ()


ModelCaller = Callable[
    [AgenticTask, str, list[dict[str, str]], int], Awaitable[AgentResponse]
]
RouteTurn = Callable[[AgenticTask, str, object, float], Awaitable[str]]
Grader = Callable[[Path], GradeResult]


def tier_at_or_above(
    routed_tier: str,
    minimum_tier: str,
    rung_order: Sequence[str] = TIERS,
) -> str:
    """Apply a monotonic rung floor without hard-coding tier transitions."""
    if routed_tier not in rung_order:
        raise ValueError(f"routed tier {routed_tier!r} is not in the rung order")
    if minimum_tier not in rung_order:
        raise ValueError(f"minimum tier {minimum_tier!r} is not in the rung order")
    selected_index = max(rung_order.index(routed_tier), rung_order.index(minimum_tier))
    return rung_order[selected_index]


def next_tier(tier: str, rung_order: Sequence[str] = TIERS) -> str:
    """Return the next configured rung, capped at the highest rung."""
    if tier not in rung_order:
        raise ValueError(f"tier {tier!r} is not in the rung order")
    return rung_order[min(rung_order.index(tier) + 1, len(rung_order) - 1)]


def load_tasks(root: Path = BENCHMARK_ROOT) -> list[AgenticTask]:
    """Load declarative task fixtures and validate their public metadata."""
    tasks: list[AgenticTask] = []
    for task_root in sorted(path for path in root.iterdir() if path.is_dir()):
        config_path = task_root / "task.toml"
        issue_path = task_root / "task.md"
        repo_root = task_root / "repo"
        grader_root = task_root / "grader_tests"
        oracle_path = task_root / "oracle.patch"
        required = (config_path, issue_path, repo_root, grader_root, oracle_path)
        if not all(path.exists() for path in required):
            raise ValueError(f"incomplete agentic task fixture: {task_root}")

        config = tomllib.loads(config_path.read_text())
        task_id = str(config["id"])
        difficulty = float(config["difficulty"])
        max_turns = int(config["max_turns"])
        if task_id != task_root.name:
            raise ValueError(f"task id {task_id!r} must match directory {task_root.name!r}")
        if not 0 <= difficulty <= 1:
            raise ValueError(f"difficulty for {task_id!r} must be between 0 and 1")
        if max_turns < 1:
            raise ValueError(f"max_turns for {task_id!r} must be at least 1")

        editable_files = tuple(
            path.relative_to(repo_root).as_posix()
            for path in sorted(repo_root.rglob("*"))
            if path.is_file()
        )
        if not editable_files:
            raise ValueError(f"agentic task {task_id!r} has no repository files")
        tasks.append(AgenticTask(
            task_id=task_id,
            root=task_root,
            issue=issue_path.read_text().strip(),
            difficulty=difficulty,
            max_turns=max_turns,
            editable_files=editable_files,
        ))

    if not tasks:
        raise ValueError(f"no agentic tasks found under {root}")
    return tasks


def materialize_task(task: AgenticTask, workspace: Path) -> None:
    """Copy the starter repository and held-out tests into an empty workspace."""
    shutil.copytree(task.root / "repo", workspace, dirs_exist_ok=True)
    shutil.copytree(task.root / "grader_tests", workspace / "grader_tests")


def repository_snapshot(workspace: Path, editable_files: Sequence[str]) -> str:
    sections = []
    for relative_path in editable_files:
        content = (workspace / relative_path).read_text()
        sections.append(f"### {relative_path}\n```python\n{content}```")
    return "\n\n".join(sections)


def initial_messages(task: AgenticTask, workspace: Path) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a repository coding agent. Return exactly one unified diff "
                "against the current repository. Modify only the listed source files. "
                "Do not add, remove, rename, or edit tests."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Issue:\n{task.issue}\n\nCurrent repository:\n"
                f"{repository_snapshot(workspace, task.editable_files)}"
            ),
        },
    ]


_FENCED_PATCH_RE = re.compile(
    r"```[^\r\n]*\r?\n(?P<body>.*?)```", re.DOTALL
)
_FORBIDDEN_PATCH_MARKERS = (
    "GIT binary patch",
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
)


def extract_unified_diff(response: str) -> str | None:
    """Extract one text unified diff from prose or a Markdown fence."""
    for match in _FENCED_PATCH_RE.finditer(response):
        candidate = match.group("body").strip()
        if "--- " in candidate and "+++ " in candidate:
            return candidate + "\n"

    start = response.find("diff --git ")
    if start >= 0:
        candidate = response[start:].strip()
        if "--- " in candidate and "+++ " in candidate:
            return candidate + "\n"
    plain_header = re.search(r"^--- [^\n]+\n\+\+\+ [^\n]+", response, re.MULTILINE)
    if plain_header:
        return response[plain_header.start():].strip() + "\n"
    return None


def _normalized_patch_path(raw_path: str) -> str | None:
    path = raw_path.split("\t", 1)[0].strip()
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        path = path[2:]
    pure = PurePosixPath(path)
    if not path or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe patch path: {raw_path!r}")
    return pure.as_posix()


def validate_patch(diff: str, editable_files: Sequence[str]) -> None:
    """Reject path traversal, test edits, file creation, deletion, and mode changes."""
    if any(marker in diff for marker in _FORBIDDEN_PATCH_MARKERS):
        raise ValueError("patch may only modify existing regular source files")

    allowed = set(editable_files)
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("--- ", "+++ ")):
            normalized = _normalized_patch_path(line[4:])
            if normalized is None:
                raise ValueError("patch may not add or delete files")
            paths.append(normalized)

    if not paths or len(paths) % 2:
        raise ValueError("response does not contain complete unified-diff headers")
    forbidden = sorted(set(paths) - allowed)
    if forbidden:
        raise ValueError(f"patch targets non-editable file(s): {', '.join(forbidden)}")


def apply_model_patch(
    workspace: Path, response: str, editable_files: Sequence[str]
) -> PatchResult:
    diff = extract_unified_diff(response)
    if diff is None:
        return PatchResult(False, "No unified diff was found in the response.")

    try:
        validate_patch(diff, editable_files)
    except ValueError as exc:
        return PatchResult(False, f"Patch rejected: {exc}")

    try:
        checked = subprocess.run(
            [
                "git", "apply", "--check", "--recount", "--unidiff-zero",
                "--whitespace=nowarn", "-",
            ],
            cwd=workspace,
            input=diff,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if checked.returncode != 0:
            detail = (checked.stderr or checked.stdout).strip()
            return PatchResult(False, f"Patch did not apply: {detail}")

        applied = subprocess.run(
            [
                "git", "apply", "--recount", "--unidiff-zero",
                "--whitespace=nowarn", "-",
            ],
            cwd=workspace,
            input=diff,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise AgenticInfrastructureError(f"could not run git apply: {exc}") from exc

    if applied.returncode != 0:
        detail = (applied.stderr or applied.stdout).strip()
        return PatchResult(False, f"Patch did not apply: {detail}")
    return PatchResult(True, "Patch applied successfully.")


class DockerGrader:
    """Execute held-out stdlib tests with no network and a read-only rootfs."""

    def __init__(self, image: str = DEFAULT_DOCKER_IMAGE, timeout_seconds: int = 30):
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.image_id: str | None = None

    def preflight(self) -> None:
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", self.image],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise AgenticInfrastructureError(f"Docker is unavailable: {exc}") from exc
        if result.returncode != 0:
            raise AgenticInfrastructureError(
                f"Docker image {self.image!r} is not available locally; run "
                f"`docker pull {self.image}` before the benchmark"
            )
        self.image_id = result.stdout.strip()

    def __call__(self, workspace: Path) -> GradeResult:
        command = [
            "docker", "run", "--rm", "--pull", "never",
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "128",
            "--memory", "256m", "--cpus", "1",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--user", "65534:65534",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "PYTHONPATH=/workspace",
            "-v", f"{workspace.resolve()}:/workspace:ro",
            "-w", "/workspace",
            self.image_id or self.image,
            "python", "-m", "unittest", "discover", "-s", "grader_tests", "-v",
        ]
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            return GradeResult(False, f"Docker is unavailable: {exc}", True)
        except subprocess.TimeoutExpired:
            return GradeResult(
                False,
                f"Tests exceeded the {self.timeout_seconds}s execution limit.",
            )

        output = (result.stdout + "\n" + result.stderr).strip()
        output = output[-MAX_OBSERVATION_CHARS:]
        return GradeResult(result.returncode == 0, output, result.returncode == 125)


async def route_agentic_turn(
    task: AgenticTask, latest_observation: str, pool, current_threshold: float
) -> str:
    routing_text = task.issue
    if latest_observation:
        routing_text += f"\n\nLatest execution observation:\n{latest_observation}"

    if pool is not None:
        try:
            from gatoway.router import classify

            return (await classify(routing_text, pool, current_threshold)).tier
        except Exception as exc:
            print(
                f"  [warn] classify() failed for {task.task_id!r} ({exc}); "
                "using its held-out difficulty label",
                flush=True,
            )

    return decide(
        similarity=0.9,
        difficulty=task.difficulty,
        matched_routing_id=None,
        input_embedding=[],
        current_threshold=current_threshold,
    ).tier


async def call_agentic_model(
    task: AgenticTask,
    tier: str,
    messages: list[dict[str, str]],
    turn: int,
) -> AgentResponse:
    del turn
    started = time.perf_counter()
    failures = []
    candidates = TIER_MODELS[tier][:2]
    for candidate_number, model in enumerate(candidates, start=1):
        generation_options = {
            "temperature": 0.0,
            "max_tokens": PROVIDER_MAX_TOKENS,
        }
        # NRP's Qwen3 endpoints otherwise spend the entire output allowance
        # in reasoning_content and frequently terminate at `length` before a
        # patch is emitted. The vLLM chat-template option requests direct
        # non-thinking output for this strict patch-generation workload.
        if "qwen3" in model:
            generation_options["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False}
            }
        try:
            response = await asyncio.wait_for(
                call_provider(model, messages, **generation_options),
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
            return AgentResponse(
                response.content,
                response.model_id,
                response.cost_cents,
                response.input_tokens,
                response.output_tokens,
                time.perf_counter() - started,
                finish_reason=response.finish_reason,
                provider_failures=tuple(failures),
            )
        except Exception as exc:  # provider exceptions are intentionally opaque
            failures.append(f"{model}: {type(exc).__name__}")
            next_step = (
                "trying the tier fallback"
                if candidate_number < len(candidates)
                else "tier fallback exhausted"
            )
            print(
                f"  [warn] {model} failed for {task.task_id} "
                f"({type(exc).__name__}); {next_step}",
                flush=True,
            )

    detail = "; ".join(failures) or "tier has no configured model"
    return AgentResponse(
        content="",
        model_id=f"provider-error/{tier}",
        cost_cents=0.0,
        latency_seconds=time.perf_counter() - started,
        provider_error=f"Provider call failed after tier fallback: {detail}",
        finish_reason="provider_error",
        provider_failures=tuple(failures),
    )


async def scripted_repair_model(
    task: AgenticTask,
    tier: str,
    messages: list[dict[str, str]],
    turn: int,
) -> AgentResponse:
    """Deterministic plumbing smoke test: fail once, then use the oracle patch."""
    del messages
    if turn == 1:
        content = "I need an execution observation before proposing the patch."
    else:
        content = f"```diff\n{task.oracle_patch}```"
    return AgentResponse(
        content,
        f"dry-run/{tier}",
        param_count_b(tier),
        finish_reason="stop",
    )


def _repair_message(observation: str, workspace: Path, task: AgenticTask) -> str:
    return (
        "The previous attempt did not pass. Diagnose this execution observation "
        "and return a corrective unified diff against the repository's current state.\n\n"
        f"Observation:\n{observation}\n\nCurrent repository:\n"
        f"{repository_snapshot(workspace, task.editable_files)}"
    )


async def run_agentic_task(
    task: AgenticTask,
    pool,
    grader: Grader,
    model_caller: ModelCaller = call_agentic_model,
    route_turn: RouteTurn = route_agentic_turn,
    rung_order: Sequence[str] = TIERS,
    fixed_tier: str | None = None,
    evaluation_path: str = "router",
) -> AgenticResult:
    attempts: list[AgenticAttempt] = []
    latest_observation = ""
    minimum_tier = fixed_tier or rung_order[0]

    with tempfile.TemporaryDirectory(prefix=f"gatoway-{task.task_id}-") as tmp:
        workspace = Path(tmp)
        materialize_task(task, workspace)
        messages = initial_messages(task, workspace)

        for turn in range(1, task.max_turns + 1):
            threshold = compute_threshold(turn, AGENTIC_EXPECTED_TURNS)
            router_tier = fixed_tier or await route_turn(
                task, latest_observation, pool, threshold
            )
            tier = (
                fixed_tier
                if fixed_tier
                else tier_at_or_above(router_tier, minimum_tier, rung_order)
            )
            messages_sent = tuple(dict(message) for message in messages)
            response = await model_caller(task, tier, messages, turn)
            patch_result = (
                PatchResult(False, response.provider_error)
                if response.provider_error
                else apply_model_patch(workspace, response.content, task.editable_files)
            )
            if (
                not patch_result.applied
                and not response.provider_error
                and response.finish_reason
            ):
                patch_result = PatchResult(
                    False,
                    f"{patch_result.observation} Model finish reason: "
                    f"{response.finish_reason}.",
                )

            tests_passed = False
            if patch_result.applied:
                grade = grader(workspace)
                if grade.infrastructure_error:
                    raise AgenticInfrastructureError(grade.output)
                tests_passed = grade.passed
                latest_observation = grade.output or "Tests failed without output."
            else:
                latest_observation = patch_result.observation

            attempts.append(AgenticAttempt(
                turn=turn,
                threshold=threshold,
                tier=tier,
                model_id=response.model_id,
                cost_cents=response.cost_cents,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_seconds=response.latency_seconds,
                patch_applied=patch_result.applied,
                tests_passed=tests_passed,
                observation=latest_observation,
                router_tier=router_tier,
                minimum_tier=minimum_tier,
                finish_reason=response.finish_reason,
                provider_failures=response.provider_failures,
                messages_sent=messages_sent,
                response_text=response.content,
            ))
            routing_detail = (
                f"router={router_tier} selected={tier}"
                if router_tier != tier
                else f"tier={tier}"
            )
            print(
                f"  [{task.task_id} turn {turn}/{task.max_turns}] "
                f"path={evaluation_path} threshold={threshold:.2f} {routing_detail} "
                f"patch={'yes' if patch_result.applied else 'no'} "
                f"tests={'PASS' if tests_passed else 'FAIL'}",
                flush=True,
            )
            if tests_passed:
                return AgenticResult(
                    task.task_id, True, tuple(attempts), evaluation_path
                )

            # Semantic confidence remains useful for the initial selection,
            # but concrete execution failure is stronger evidence. Raise a
            # monotonic floor one configured rung for the next repair. This
            # also moves cross-rung after both models in a tier fail.
            minimum_tier = next_tier(tier, rung_order)

            messages.extend([
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": _repair_message(latest_observation, workspace, task)},
            ])

    return AgenticResult(task.task_id, False, tuple(attempts), evaluation_path)


def write_trajectory(task: AgenticTask, result: AgenticResult, artifact_dir: Path) -> Path:
    """Persist a complete per-turn transcript for reproducible diagnosis."""
    path = artifact_dir / result.evaluation_path / f"{task.task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task.task_id,
        "evaluation_path": result.evaluation_path,
        "issue": task.issue,
        "passed": result.passed,
        "attempts": [
            {
                "turn": attempt.turn,
                "threshold": attempt.threshold,
                "router_tier": attempt.router_tier,
                "minimum_tier": attempt.minimum_tier,
                "selected_tier": attempt.tier,
                "model_id": attempt.model_id,
                "finish_reason": attempt.finish_reason,
                "provider_failures": list(attempt.provider_failures),
                "input_tokens": attempt.input_tokens,
                "output_tokens": attempt.output_tokens,
                "latency_seconds": attempt.latency_seconds,
                "patch_applied": attempt.patch_applied,
                "tests_passed": attempt.tests_passed,
                "messages_sent": list(attempt.messages_sent),
                "response_text": attempt.response_text,
                "observation": attempt.observation,
            }
            for attempt in result.attempts
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


async def run_suite(
    tasks: Sequence[AgenticTask],
    pool,
    grader: Grader,
    model_caller: ModelCaller = call_agentic_model,
    rung_order: Sequence[str] = TIERS,
    include_baseline: bool = True,
    artifact_dir: Path | None = None,
) -> AgenticEvalRun:
    router_results: list[AgenticResult] = []
    baseline_results: list[AgenticResult] = []
    for task in tasks:
        router_result = await run_agentic_task(
            task,
            pool,
            grader,
            model_caller=model_caller,
            rung_order=rung_order,
            evaluation_path="router",
        )
        router_results.append(router_result)
        if artifact_dir:
            write_trajectory(task, router_result, artifact_dir)

        if include_baseline:
            baseline_result = await run_agentic_task(
                task,
                pool,
                grader,
                model_caller=model_caller,
                rung_order=rung_order,
                fixed_tier=rung_order[-1],
                evaluation_path="always_frontier",
            )
            baseline_results.append(baseline_result)
            if artifact_dir:
                write_trajectory(task, baseline_result, artifact_dir)

    return AgenticEvalRun(tuple(router_results), tuple(baseline_results))


def production_readiness_gate(
    runs: Sequence[Sequence[AgenticResult]],
) -> tuple[bool, str]:
    """Require repeatability per task and no fully exhausted provider attempt."""
    if len(runs) < 3:
        return False, f"not evaluated: {len(runs)}/3 required runs"

    required_passes = (2 * len(runs) + 2) // 3
    task_ids = [result.task_id for result in runs[0]]
    unreliable = []
    for task_id in task_ids:
        passes = sum(
            result.passed
            for run in runs
            for result in run
            if result.task_id == task_id
        )
        if passes < required_passes:
            unreliable.append(f"{task_id} passed {passes}/{len(runs)}")

    exhausted = sum(
        attempt.model_id.startswith("provider-error/")
        for run in runs
        for result in run
        for attempt in result.attempts
    )
    failures = list(unreliable)
    if exhausted:
        failures.append(f"{exhausted} attempt(s) exhausted both tier models")
    if failures:
        return False, "; ".join(failures)
    return True, f"every task passed at least {required_passes}/{len(runs)} with no exhausted tier"


def build_report(
    runs: Sequence[AgenticEvalRun],
    dry_run: bool,
    db_backed: bool,
    grader_image: str | None = None,
    artifact_dir: Path | None = None,
) -> str:
    if not runs or not all(run.router_results for run in runs):
        raise ValueError("at least one non-empty agentic run is required")

    router_runs = [list(run.router_results) for run in runs]
    baseline_runs = [list(run.baseline_results) for run in runs]
    flat_router = [result for run in router_runs for result in run]
    flat_baseline = [result for run in baseline_runs for result in run]
    gate_passed, gate_detail = production_readiness_gate(router_runs)
    mode = "scripted repair smoke test" if dry_run else "live NRP model calls"
    routing = "DB-backed pgvector" if db_backed else "held-out difficulty fallback"

    def summary(label: str, results: Sequence[AgenticResult]) -> str:
        passed = sum(result.passed for result in results)
        first_pass = sum(
            result.passed and len(result.attempts) == 1 for result in results
        )
        attempts = sum(len(result.attempts) for result in results)
        switches = sum(result.tier_switches for result in results)
        tokens = sum(result.total_tokens for result in results)
        seconds = sum(result.provider_latency_seconds for result in results)
        return (
            f"**{label}: solved {passed}/{len(results)} ({passed / len(results):.0%}); "
            f"first-pass {first_pass}/{len(results)} ({first_pass / len(results):.0%}); "
            f"mean turns {attempts / len(results):.2f}; tier switches {switches}; "
            f"tokens {tokens:,}; provider latency {seconds:.1f}s.**"
        )

    lines = [
        "# Agentic Coding Eval Report",
        "",
        f"_Mode: {mode}; routing: {routing}; {len(runs)} run(s). Accepted patches "
        "were executed in a network-disabled, resource-limited Docker container._",
        "",
        summary("Router", flat_router),
        "",
        f"**Production readiness gate: {'PASS' if gate_passed else 'FAIL'} — "
        f"{gate_detail}.**",
    ]
    if flat_baseline:
        baseline_passed, baseline_detail = production_readiness_gate(baseline_runs)
        router_cost = sum(result.total_cost_cents for result in flat_router)
        baseline_cost = sum(result.total_cost_cents for result in flat_baseline)
        router_latency = sum(result.provider_latency_seconds for result in flat_router)
        baseline_latency = sum(
            result.provider_latency_seconds for result in flat_baseline
        )
        cost_reduction = (
            (baseline_cost - router_cost) / baseline_cost * 100
            if baseline_cost
            else 0.0
        )
        latency_reduction = (
            (baseline_latency - router_latency) / baseline_latency * 100
            if baseline_latency
            else 0.0
        )
        lines.extend([
            "",
            summary("Always-frontier baseline", flat_baseline),
            "",
            f"**Baseline readiness gate: {'PASS' if baseline_passed else 'FAIL'} — "
            f"{baseline_detail}.**",
            "",
            f"**Router vs baseline: {cost_reduction:.1f}% lower compute/cost proxy "
            f"and {latency_reduction:.1f}% lower provider latency.**",
        ])
    lines.extend([
        "",
        "| Run | Path | Task | Result | Turns | Tier path | Model path | Tokens | Provider latency | Compute/cost proxy | Failure |",
        "|---:|---|---|---|---:|---|---|---:|---:|---:|---|",
    ])
    if grader_image:
        lines[2] = lines[2][:-1] + f" Grader image: `{grader_image}`._"
    for run_number, run in enumerate(runs, start=1):
        for result in (*run.router_results, *run.baseline_results):
            failure = "—"
            if not result.passed:
                last = result.attempts[-1]
                failure = (
                    "Provider failure"
                    if last.observation.startswith("Provider call failed")
                    else "No applicable diff"
                    if not last.patch_applied
                    else "Held-out tests failed"
                )
            lines.append(
                f"| {run_number} | {result.evaluation_path} | {result.task_id} | "
                f"{'PASS' if result.passed else 'FAIL'} | {len(result.attempts)} | "
                f"{' → '.join(result.tiers)} | {' → '.join(result.models)} | "
                f"{result.total_tokens:,} | "
                f"{result.provider_latency_seconds:.1f}s | {result.total_cost_cents:.3f} | "
                f"{failure} |"
            )
    lines.append("")
    if artifact_dir:
        try:
            artifact_label = artifact_dir.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            artifact_label = str(artifact_dir)
        lines.extend([
            f"Full per-turn prompts, responses, finish reasons, provider failures, "
            f"and grader observations: `{artifact_label}`.",
            "",
        ])
    if dry_run:
        lines.append(
            "A dry run deliberately emits no patch on turn one and applies the task's "
            "oracle patch on turn two. It verifies isolation, feedback chaining, patch "
            "application, execution scoring, and threshold-driven routing; it is not a "
            "model-quality result."
        )
    else:
        if len(runs) < 3:
            lines.append(
                "This is a live model-quality measurement. Treat a single run as an initial "
                "observation; use at least three runs before making a stability claim."
            )
        else:
            lines.append(
                "This is a repeated live model-quality measurement. Timed-out calls that "
                "returned no usage metadata contribute to provider latency but not to the "
                "token or compute/cost proxy totals."
            )
    return "\n".join(lines)


async def _try_get_pool():
    try:
        from gatoway.db import get_pool

        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        return pool
    except Exception as exc:
        print(f"[info] Postgres unavailable ({exc}); using standalone routing.")
        return None


async def _main(args: argparse.Namespace) -> None:
    tasks = load_tasks()
    if args.task:
        requested = set(args.task)
        tasks = [task for task in tasks if task.task_id in requested]
        missing = sorted(requested - {task.task_id for task in tasks})
        if missing:
            raise SystemExit(f"unknown task(s): {', '.join(missing)}")

    grader = DockerGrader(args.docker_image, args.test_timeout)
    grader.preflight()
    pool = await _try_get_pool()
    invocation_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = Path(args.artifacts_dir) / invocation_id
    runs: list[AgenticEvalRun] = []
    try:
        for run_number in range(1, args.runs + 1):
            print(f"[run {run_number}/{args.runs}]", flush=True)
            runs.append(await run_suite(
                tasks,
                pool,
                grader,
                model_caller=scripted_repair_model if args.dry_run else call_agentic_model,
                include_baseline=not args.skip_baseline,
                artifact_dir=artifact_dir / f"run-{run_number:03d}",
            ))
    finally:
        if pool is not None:
            from gatoway.db import close_pool

            await close_pool()

    image_identity = (
        f"{args.docker_image} ({grader.image_id})"
        if grader.image_id
        else args.docker_image
    )
    report = build_report(
        runs,
        args.dry_run,
        pool is not None,
        grader_image=image_identity,
        artifact_dir=artifact_dir,
    )
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report + "\n")
    print(report)
    print(f"\n[info] Wrote report to {report_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gatoway agentic coding eval")
    parser.add_argument("--dry-run", action="store_true", help="Use scripted repair/oracle responses.")
    parser.add_argument("--runs", type=int, default=1, help="Number of repeated benchmark runs.")
    parser.add_argument("--task", action="append", help="Run only this task ID (repeatable).")
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Skip the fresh-workspace always-frontier control.",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=str(ARTIFACT_ROOT),
        help="Directory for raw per-turn trajectory artifacts.",
    )
    parser.add_argument(
        "--report-path",
        default=str(REPORT_PATH),
        help="Markdown report output path.",
    )
    parser.add_argument("--docker-image", default=DEFAULT_DOCKER_IMAGE)
    parser.add_argument("--test-timeout", type=int, default=30)
    return parser.parse_args()


if __name__ == "__main__":
    parsed = _parse_args()
    if parsed.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if parsed.test_timeout < 1:
        raise SystemExit("--test-timeout must be at least 1")
    if not parsed.dry_run and not os.environ.get("NRP_API_KEY"):
        print("[info] No NRP_API_KEY set -- auto-falling back to --dry-run.")
        parsed.dry_run = True
    try:
        asyncio.run(_main(parsed))
    except AgenticInfrastructureError as exc:
        raise SystemExit(f"agentic eval infrastructure error: {exc}") from exc
