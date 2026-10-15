"""Fractional hidden-test grading. Generated code runs only inside Docker."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from gatoway.sandbox import docker_command


class CodeInfrastructureError(RuntimeError):
    """The execution environment failed; no model score can be recorded."""


IMAGES = {"python": "python:3.13-slim", "typescript": "node:22-slim"}
TEST_FILES = {"python": "test_hidden.py", "typescript": "hidden.test.ts"}
EXTENSIONS = {"python": "py", "typescript": "ts"}


def extract_code(response: str, language: str) -> str | None:
    aliases = {"python": {"python", "py"}, "typescript": {"typescript", "ts"}}[language]
    blocks = re.findall(r"\x60{3}([^\n\x60]*?)\n(.*?)\x60{3}", response, re.DOTALL)
    tagged = [body.strip() for tag, body in blocks if tag.strip().lower() in aliases]
    untagged = [body.strip() for tag, body in blocks if not tag.strip()]
    choices = tagged or untagged
    return choices[-1] if choices else None


def test_command(language: str) -> list[str]:
    if language == "python":
        return ["python", "-m", "unittest", "-v", "test_hidden"]
    if language == "typescript":
        return ["node", "--experimental-transform-types", "--test",
                "--test-reporter=tap", "hidden.test.ts"]
    raise ValueError(f"unsupported language: {language}")


def parse_score(language: str, output: str, returncode: int) -> float:
    if returncode not in (0, 1):
        return 0.0
    if language == "python":
        totals = re.findall(r"^Ran (\d+) tests? in ", output, re.MULTILINE)
        if not totals:
            return 0.0
        total = int(totals[-1])
        summaries = re.findall(r"^(OK(?: \(.*\))?|FAILED \(.*\))$", output, re.MULTILINE)
        if not summaries:
            return 0.0
        summary = summaries[-1]
        counts = dict(re.findall(r"(failures|errors|skipped|expected failures|unexpected successes)=(\d+)", summary))
        failed = sum(int(value) for value in counts.values())
        if (returncode == 0) != summary.startswith("OK"):
            return 0.0
        passed = total - failed
    else:
        def count(label):
            matches = re.findall(rf"^# {label} (\d+)\s*$", output, re.MULTILINE)
            return int(matches[-1]) if matches else None
        total, passed, failed = count("tests"), count("pass"), count("fail")
        if total is None or passed is None or failed is None:
            return 0.0
        if returncode == 0 and failed:
            return 0.0
        if returncode == 1 and failed == 0:
            return 0.0
    if not total or not 0 <= passed <= total:
        return 0.0
    return passed / total


class CodeGrader:
    def __init__(self, timeout_seconds: float = 30, runner=None):
        self.timeout_seconds = timeout_seconds
        self.runner = runner or subprocess.run
        self.images: dict[str, str] = {}

    def preflight(self, language: str) -> None:
        if language in self.images:
            return
        candidates = [IMAGES[language]]
        if language == "typescript":
            candidates.append("node:24-slim")
        for image in candidates:
            try:
                result = self.runner(
                    ["docker", "image", "inspect", "--format", "{{.Id}}", image],
                    capture_output=True, text=True, timeout=10, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise CodeInfrastructureError(f"Docker unavailable: {exc}") from exc
            if result.returncode or not result.stdout.strip():
                continue
            image_id = result.stdout.strip()
            if language == "typescript":
                # Probe the selected image itself, including enum syntax.
                with tempfile.TemporaryDirectory() as directory:
                    workspace = Path(directory)
                    workspace.chmod(0o755)
                    probe = workspace / "probe.ts"
                    probe.write_text(
                        "enum Check { OK = 7 }; if (Check.OK !== 7) process.exit(1);\n"
                    )
                    probe.chmod(0o644)
                    result = self._run(workspace, image_id,
                                       ["node", "--experimental-transform-types", "probe.ts"])
                    if result is None or result.returncode:
                        continue
            self.images[language] = image_id
            return
        raise CodeInfrastructureError(
            f"No compatible Docker image for {language}; start Docker and pull "
            + " or ".join(candidates)
        )

    def _run(self, workspace: Path, image: str, command: list[str]):
        name = "gatoway-code-" + uuid.uuid4().hex
        try:
            return self.runner(
                docker_command(workspace, image, command, name=name),
                capture_output=True, text=True, timeout=self.timeout_seconds, check=False,
            )
        except OSError as exc:
            raise CodeInfrastructureError(f"Docker unavailable: {exc}") from exc
        except subprocess.TimeoutExpired:
            return None
        finally:
            # Killing the docker client alone leaves the container running.
            try:
                self.runner(["docker", "rm", "-f", name], capture_output=True,
                            text=True, timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise CodeInfrastructureError(f"Could not clean up container {name}") from exc

    def grade(self, response: str, task_dir: Path, language: str) -> float:
        code = extract_code(response, language)
        if not code:
            return 0.0
        self.preflight(language)
        with tempfile.TemporaryDirectory(prefix="gatoway-code-") as directory:
            workspace = Path(directory)
            workspace.chmod(0o755)
            solution = workspace / f"solution.{EXTENSIONS[language]}"
            solution.write_text(code)
            solution.chmod(0o644)
            hidden = workspace / TEST_FILES[language]
            shutil.copyfile(task_dir / TEST_FILES[language], hidden)
            hidden.chmod(0o644)
            result = self._run(workspace, self.images[language], test_command(language))
        if result is None:
            return 0.0
        if result.returncode in (125, 126, 127):
            raise CodeInfrastructureError(f"Docker could not execute tests: {result.stderr}")
        # ponytail: runner summaries suit cooperative answers, not adversarial
        # graders. Use an external result channel for hostile code.
        return parse_score(language, result.stdout + "\n" + result.stderr, result.returncode)

    def grade_loop(self, response: str, fixtures=None) -> float:
        """Run the legacy constrained loop task in Docker for live answers."""
        from gatoway.eval import _python_candidates, _safe_python_tree
        import textwrap

        if fixtures is None:
            fixtures = tuple((values, [(value,) for value in values])
                             for values in ([10, 20, 30], [7], []))
        if not fixtures:
            raise ValueError("execution scoring requires at least one fixture")
        if re.search(r"^\s*(?:from\s+\S+\s+import|import|while|def|class)\b",
                     response, re.MULTILINE):
            return 0.0
        with tempfile.TemporaryDirectory() as directory:
            task_dir = Path(directory)
            tests = "import unittest\nfrom solution import run_loop\n\nclass Loops(unittest.TestCase):\n"
            for i, (values, expected) in enumerate(fixtures):
                tests += (
                    f"    def test_{i}(self):"
                    f"\n        printed=[]\n"
                    f"        run_loop({values!r}, {len(values)}, lambda *args: printed.append(args))\n"
                    f"        self.assertEqual(printed, {expected!r})\n"
                )
            (task_dir / "test_hidden.py").write_text(tests)
            for candidate in _python_candidates(response):
                if _safe_python_tree(candidate) is None:
                    continue
                wrapped = "def run_loop(arr, n, print):\n" + textwrap.indent(candidate, "    ")
                fence = chr(96) * 3
                if self.grade(f"{fence}python\n{wrapped}\n{fence}", task_dir, "python") == 1:
                    return 1.0
        return 0.0
