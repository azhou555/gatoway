"""Load checked-in coding and design task artifacts without provider calls."""

from dataclasses import dataclass
from pathlib import Path
import tomllib

TASK_ROOT = Path(__file__).resolve().parent.parent / "benchmarks" / "coding"


@dataclass(frozen=True)
class CodingTask:
    task_id: str
    split: str
    language: str
    neighborhood: str
    entrypoint: str
    prompt: str
    reference: str
    rubric: list[str]
    difficulty: float
    directory: Path


def load_tasks(split: str) -> list[CodingTask]:
    if split not in {"train", "eval"}:
        raise ValueError("split must be train or eval")
    result = []
    for directory in sorted((TASK_ROOT / split).iterdir()):
        if not directory.is_dir():
            continue
        meta = tomllib.loads((directory / "task.toml").read_text())
        language = meta["language"]
        extension = {"python": "py", "typescript": "ts", "design": "md"}[language]
        result.append(CodingTask(
            task_id=directory.name, split=split, language=language,
            neighborhood=meta["neighborhood"], entrypoint=meta["entrypoint"],
            prompt=(directory / "prompt.md").read_text().strip(),
            reference=(directory / f"reference.{extension}").read_text(),
            rubric=meta.get("rubric", []), difficulty=meta.get("difficulty", 0.0),
            directory=directory,
        ))
    return result


def fenced_reference(task: CodingTask) -> str:
    if task.language == "design":
        return task.reference
    fence = chr(96) * 3
    return f"{fence}{task.language}\n{task.reference}{fence}"
