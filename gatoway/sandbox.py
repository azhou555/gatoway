"""Shared container isolation for benchmark graders."""

from pathlib import Path


def docker_command(workspace: Path, image: str, command: list[str], *,
                   name: str | None = None) -> list[str]:
    return [
        "docker", "run", "--rm", "--pull", "never",
        *(["--name", name] if name else []),
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "128",
        "--memory", "256m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--user", "65534:65534",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTHONPATH=/workspace",
        "-v", f"{workspace.resolve()}:/workspace:ro",
        "-w", "/workspace", image, *command,
    ]
