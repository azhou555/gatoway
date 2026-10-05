"""Train prompts, reference answers, and source-level eval separation checks.

Each neighborhood has at least two distinct instances. Execution tasks supply
trusted fixtures to the existing scorers; reference answers support offline
validation and the future bootstrap dry run. No difficulty is assigned here:
the bootstrap harness will derive it from observed model outcomes.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from typing import Protocol
from pathlib import Path

from gatoway.coding_tasks import load_tasks, fenced_reference
from gatoway.rubrics import RUBRICS


class PromptRecord(Protocol):
    prompt: str


def assert_no_eval_overlap(prompts: Iterable[str | PromptRecord]) -> None:
    """Reject normalized exact matches and character similarity >= 0.85.

    Accept raw strings or corpus records exposing ``prompt``. Report every
    collision so a corpus edit can fix all offending pairs at once.
    """
    from gatoway.eval import benchmark_tasks

    # ponytail: character similarity catches copied/reworded text, not semantic
    # equivalence; add task-specific semantic checks as the corpus expands.
    collisions = []
    for item in prompts:
        prompt = item if isinstance(item, str) else item.prompt
        normalized = " ".join(prompt.casefold().split())
        for task in benchmark_tasks("expanded"):
            target = " ".join(task.prompt.casefold().split())
            ratio = SequenceMatcher(None, normalized, target).ratio()
            if normalized == target or ratio >= 0.85:
                kind = "exact match" if normalized == target else "near match"
                collisions.append(
                    f"{kind}: {prompt!r} overlaps {task.task_id} "
                    f"({task.prompt!r}); ratio={ratio:.3f}"
                )
    if collisions:
        raise AssertionError("Eval prompt overlap:\n" + "\n".join(collisions))


# The fixtures are trusted corpus data. Model responses still go through the
# existing constrained Python/SQL evaluators.
@dataclass(frozen=True)
class TrainPrompt:
    prompt_id: str
    prompt: str
    scoring_method: str
    expected: list[str]
    neighborhood: str
    reference_response: str
    execution_fixtures: tuple[tuple[list[int], list[tuple[object, ...]]], ...] | None = None
    split: str = "train"
    rubric: list[str] = field(default_factory=list)
    task_dir: Path | None = None
    language: str = ""


# ponytail: exact_match remains substring-based; use answer-aware numeric and
# symbolic scoring when these legacy tasks require stricter correctness.
# Live open-ended answers use rubrics; only dry runs use the heuristic stub.
TRAIN_PROMPTS: list[TrainPrompt] = [
    TrainPrompt(
        "capital_portugal", "Name Portugal's capital city.",
        "exact_match", ["lisbon"], "factual recall", "Lisbon.",
    ),
    TrainPrompt(
        "capital_kenya", "Which city serves as Kenya's national capital?",
        "exact_match", ["nairobi"], "factual recall", "Nairobi.",
    ),
    TrainPrompt(
        "capital_peru", "Identify the capital city of Peru.",
        "exact_match", ["lima"], "factual recall", "Lima.",
    ),
    TrainPrompt(
        "multiply_24_16", "Calculate the product of 24 and 16.",
        "exact_match", ["384"], "arithmetic", "384",
    ),
    TrainPrompt(
        "multiply_32_14", "Multiply 32 by 14 and give the resulting integer.",
        "exact_match", ["448"], "arithmetic", "448",
    ),
    TrainPrompt(
        "multiply_19_26", "Evaluate 19 multiplied by 26.",
        "exact_match", ["494"], "arithmetic", "494",
    ),
    TrainPrompt(
        "fahrenheit_86", "A thermometer reads 86 F. Express that temperature in Celsius.",
        "exact_match", ["30"], "unit conversion", "30 degrees Celsius.",
    ),
    TrainPrompt(
        "fahrenheit_14", "What Celsius temperature corresponds to a reading of 14 F?",
        "exact_match", ["-10"], "unit conversion", "-10 degrees Celsius.",
    ),
    TrainPrompt(
        "quadratic_4_7", "Find both roots of the polynomial x² - 11x + 28.",
        "exact_match", ["4", "7"], "algebra", "The roots are 4 and 7.",
    ),
    TrainPrompt(
        "quadratic_negative_2_5", "Determine the zeros of x² - 3x - 10.",
        "exact_match", ["-2", "5"], "algebra", "The zeros are -2 and 5.",
    ),
    TrainPrompt(
        "loop_skip_last",
        "Given arr and n=len(arr), repair this loop so it prints each element "
        "except the last, one per line: for i in range(n): print(arr[i]). "
        "Use one for loop; empty and singleton arrays should print nothing.",
        "python_execution", [], "loop/off-by-one fixes",
        "for i in range(n-1): print(arr[i])",
        (([10, 20, 30], [(10,), (20,)]), ([7], []), ([], []),
         ([4, 4, 9, 2], [(4,), (4,), (9,)])),
    ),
    TrainPrompt(
        "loop_skip_first",
        "For arr with n=len(arr), print all items after the first, one per line. "
        "The current loop starts at index 2 and skips too much. Supply a single "
        "corrected for loop that also works for empty or singleton arrays.",
        "python_execution", [], "loop/off-by-one fixes",
        "for i in range(1, n): print(arr[i])",
        (([10, 20, 30], [(20,), (30,)]), ([7], []), ([], []),
         ([4, 4, 9, 2], [(4,), (9,), (2,)])),
    ),
    TrainPrompt(
        "loop_index_value",
        "Print each zero-based index followed by its item from arr using "
        "print(index, item). Fix the indexing in "
        "for i in range(1, n+1): print(i, arr[i]), where n=len(arr). "
        "Return one for loop, including correct behavior for an empty array.",
        "python_execution", [], "loop/off-by-one fixes",
        "for i in range(n): print(i, arr[i])",
        (([10, 20, 30], [(0, 10), (1, 20), (2, 30)]),
         ([7], [(0, 7)]), ([], []), ([4, 4], [(0, 4), (1, 4)])),
    ),
    TrainPrompt(
        "salary_maximum",
        "Using employees(id, name, salary), return the maximum salary as one "
        "SQL scalar aggregate. An empty table should return NULL.",
        "sql_execution", [], "SQL aggregate queries",
        "SELECT MAX(salary) FROM employees;",
        (([100, 100, 90, 80], [(100,)]), ([50, 40, 40, 30], [(50,)]),
         ([7], [(7,)]), ([], [(None,)]), ([-8, -3], [(-3,)])),
    ),
    TrainPrompt(
        "salary_third",
        "Query employees(id, name, salary) for its third-largest distinct salary. "
        "Ignore duplicate amounts; return no rows if fewer than three distinct "
        "amounts exist. Return exactly one column named salary containing the amount, "
        "not employee records. Use a read-only SQL SELECT.",
        "sql_execution", [], "SQL aggregate queries",
        "SELECT DISTINCT salary FROM employees ORDER BY salary DESC LIMIT 1 OFFSET 2;",
        (([100, 100, 90, 80], [(80,)]), ([50, 40, 40, 30], [(30,)]),
         ([7, 3], []), ([], []), ([4, 4, 4], [])),
    ),
    TrainPrompt(
        "salary_top_two",
        "Return the two largest distinct salary amounts from employees(id, name, "
        "salary), in descending order, using SQL. Return the available amounts "
        "when fewer than two exist.",
        "sql_execution", [], "SQL aggregate queries",
        "SELECT DISTINCT salary FROM employees ORDER BY salary DESC LIMIT 2;",
        (([100, 100, 90, 80], [(100,), (90,)]),
         ([50, 40, 40, 30], [(50,), (40,)]), ([7], [(7,)]),
         ([], []), ([4, 4, 4], [(4,)])),
    ),
    TrainPrompt(
        "shared_database_split",
        "Outline three stages for separating two teams' shared database. Address "
        "competing writers, synchronization during cutover, and recovery.",
        "llm_judge", ["ownership", "outbox", "validation", "rollback"], "systems planning",
        "1) Establish ownership of every table and route writes to a single owning "
        "team to remove contention. 2) Backfill the new stores, then use a transactional "
        "outbox to replicate changes without unsafe dual writes. 3) Run validation "
        "of row counts and invariants before switching readers; retain a rollback "
        "path and monitor replication lag.",
    ),
    TrainPrompt(
        "database_column_rollout",
        "Describe a safe three-stage rollout for renaming a database column while "
        "old and new application versions run concurrently.",
        "llm_judge", ["expand", "backfill", "compatibility", "rollback"], "systems planning",
        "1) Expand the schema with the new column while retaining the old one for "
        "compatibility. 2) Deploy code that maintains both columns and backfill "
        "existing rows in bounded batches; validate equality before switching reads. "
        "3) After all old binaries retire, remove the old column in a later release. "
        "Keep a rollback window before the destructive step.",
    ),
    TrainPrompt(
        "infinitely_many_primes",
        "Give a contradiction proof that the set of prime numbers is infinite.",
        "llm_judge", ["contradiction", "product", "divisor", "remainder"], "proofs",
        "Assume for contradiction that p1 through pk list every prime. Form the "
        "product p1*...*pk and add one. This integer exceeds one, so it has a prime "
        "divisor. Dividing it by any listed prime leaves remainder one, so none of "
        "those primes is its divisor. A prime is missing from the allegedly complete "
        "list, giving the required contradiction.",
    ),
    TrainPrompt(
        "sum_first_odd_numbers",
        "Prove by induction that the sum of the first n positive odd integers is n² "
        "for every positive integer n.",
        "llm_judge", ["base case", "hypothesis", "2n+1", "induction"], "proofs",
        "The base case n=1 holds because 1=1². For the induction hypothesis assume "
        "the first n positive odd integers sum to n². The next odd integer is 2n+1, "
        "so the sum through the next term is n²+2n+1=(n+1)². This proves the "
        "induction step, and therefore the identity holds for every positive integer.",
    ),
]


# Load new artifacts only after defining the original records. No eval module
# import is needed here, keeping the overlap guard's dependency lazy.
TRAIN_PROMPTS = [
    replace(task, rubric=RUBRICS.get(task.prompt_id, [])) for task in TRAIN_PROMPTS
]
for artifact in load_tasks("train"):
    TRAIN_PROMPTS.append(TrainPrompt(
        prompt_id=artifact.task_id, prompt=artifact.prompt,
        scoring_method="llm_judge" if artifact.language == "design" else "code_tests",
        expected=[], neighborhood=artifact.neighborhood,
        reference_response=fenced_reference(artifact), rubric=artifact.rubric,
        task_dir=artifact.directory, language=artifact.language,
    ))


async def score(task, response: str, answer_model: str, *, dry_run: bool = False,
                grader=None) -> float:
    """Shared live scorer for evaluation and measured bank bootstrap."""
    import asyncio
    from gatoway.eval import score_task
    if task.scoring_method == "llm_judge" and not dry_run:
        from gatoway.judge import judge
        return await judge(task.prompt, response, task.rubric, answer_model)
    if task.scoring_method == "python_execution" and not dry_run:
        from gatoway.code_grader import CodeGrader
        grader = grader or CodeGrader()
        return await asyncio.to_thread(
            grader.grade_loop, response, getattr(task, "execution_fixtures", None)
        )
    if task.scoring_method == "code_tests":
        if dry_run:
            # Scripted smoke scores only; never used to populate the bank.
            return float(response == task.reference_response)
        from gatoway.code_grader import CodeGrader
        grader = grader or CodeGrader()
        return await asyncio.to_thread(grader.grade, response, task.task_dir, task.language)
    return score_task(task, response, dry_run=dry_run)
