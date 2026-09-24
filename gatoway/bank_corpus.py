"""Train-split prompt corpus for bootstrapping the decision_history bank
(docs/plans/2026-09-24-bank-densification.md).

Every prompt written into the bank must stay clear of the eval split
(SPEC.md §7/§8): the router matches on input embeddings, so a seed prompt that
restates a BENCHMARK_TASKS prompt hands that task a near-1.0 similarity match
and the gate measures seeding instead of routing.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from gatoway.eval import (
    BENCHMARK_TASKS,
    score_python_execution,
    score_sql_execution,
    score_task,
)

# ponytail: character-level ratio catches restatements, not paraphrases. An
# embedding-similarity check against the router's own threshold is the upgrade
# if a reworded leak ever slips through.
OVERLAP_RATIO_LIMIT = 0.85


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def eval_overlaps(prompts: list[str]) -> list[tuple[str, str, float]]:
    """(prompt, eval task_id, ratio) for every prompt that is an exact
    (normalized) copy of, or too similar to, an eval-split prompt."""
    hits = []
    for prompt in prompts:
        for task in BENCHMARK_TASKS:
            a, b = _normalize(prompt), _normalize(task.prompt)
            ratio = 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()
            if ratio >= OVERLAP_RATIO_LIMIT:
                hits.append((prompt, task.task_id, round(ratio, 3)))
    return hits


def assert_no_eval_overlap(prompts: list[str]) -> None:
    hits = eval_overlaps(prompts)
    assert not hits, "train prompts overlap the eval split:\n" + "\n".join(
        f"  {ratio:.2f}  {task_id}  <-  {prompt!r}" for prompt, task_id, ratio in hits
    )


@dataclass(frozen=True)
class TrainPrompt:
    prompt_id: str
    prompt: str
    scoring_method: str  # same methods as eval.BenchmarkTask
    expected: list[str]  # exact_match substrings / llm_judge keywords
    neighborhood: str  # the eval cluster this prompt densifies
    # A known-good answer: proves the prompt is scoreable, and doubles as the
    # canned response for bootstrap --dry-run.
    reference: str
    # Execution scorers only. These must differ from the eval task's fixtures,
    # or the train prompt is the eval task reworded.
    fixtures: tuple = ()
    sql_functions: frozenset[str] = frozenset()


def score(prompt: TrainPrompt, response: str) -> float:
    if prompt.scoring_method == "python_execution":
        return score_python_execution(response, prompt.fixtures)
    if prompt.scoring_method == "sql_execution":
        return score_sql_execution(response, prompt.fixtures, prompt.sql_functions)
    return score_task(prompt, response)


def _prints(transform) -> tuple:
    """Python fixtures: expected print() calls for three arr contents."""
    return tuple((values, transform(values)) for values in ([10, 20, 30, 40, 50], [7], []))


_ORDERS = "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, total INTEGER);"
_PRODUCTS = "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price INTEGER);"


def _insert(table: str, columns: str, rows: list[tuple]) -> str:
    values = ", ".join(repr(row) for row in rows)
    return f"INSERT INTO {table} ({columns}) VALUES {values};"


TRAIN_PROMPTS: list[TrainPrompt] = [
    # --- factual recall (near capital_france) ---
    TrainPrompt("capital_canada", "Which city is the capital of Canada?",
                "exact_match", ["ottawa"], "factual_recall",
                "The capital of Canada is Ottawa."),
    TrainPrompt("largest_ocean", "What is the largest ocean on Earth?",
                "exact_match", ["pacific"], "factual_recall",
                "The Pacific Ocean is the largest."),
    TrainPrompt("mona_lisa", "Who painted the Mona Lisa?",
                "exact_match", ["leonardo"], "factual_recall",
                "Leonardo da Vinci painted the Mona Lisa."),
    # --- arithmetic ---
    TrainPrompt("mult_19_24", "Compute 19 times 24.",
                "exact_match", ["456"], "arithmetic", "19 * 24 = 456."),
    TrainPrompt("div_add", "What is 144 divided by 12, plus 35?",
                "exact_match", ["47"], "arithmetic", "144 / 12 = 12, and 12 + 35 = 47."),
    TrainPrompt("mult_37_29", "Multiply 37 by 29.",
                "exact_match", ["1073"], "arithmetic", "37 * 29 = 1073."),
    # --- unit conversion ---
    TrainPrompt("km_to_miles", "How many miles is 100 kilometers, rounded to the nearest whole mile?",
                "exact_match", ["62"], "unit_conversion", "100 km is about 62 miles."),
    TrainPrompt("c_to_f", "Convert 25 degrees Celsius to Fahrenheit.",
                "exact_match", ["77"], "unit_conversion", "25 C = 25 * 9/5 + 32 = 77 F."),
    # --- algebra ---
    TrainPrompt("linear_eq", "Solve 3x + 7 = 22 for x.",
                "exact_match", ["5"], "algebra", "3x = 15, so x = 5."),
    TrainPrompt("quadratic_neg_root", "Find both roots of x^2 + x - 12 = 0.",
                "exact_match", ["3", "-4"], "algebra", "(x + 4)(x - 3) = 0, so x = 3 or x = -4."),
    # --- loop fixes (near code_fix); every target differs from "print all" ---
    TrainPrompt("every_other",
                "Fix the range() call so this loop prints every other element of arr, "
                "starting at index 0: for i in range(0, n): print(arr[i])",
                "python_execution", [], "loop_fix",
                "for i in range(0, n, 2): print(arr[i])",
                fixtures=_prints(lambda v: [(x,) for x in v[::2]])),
    TrainPrompt("skip_first",
                "Fix the range() call so this loop prints every element of arr except "
                "the first one: for i in range(0, n): print(arr[i])",
                "python_execution", [], "loop_fix",
                "for i in range(1, n): print(arr[i])",
                fixtures=_prints(lambda v: [(x,) for x in v[1:]])),
    TrainPrompt("index_value",
                "This loop should print each index of arr together with its value, "
                "starting from index 0, but it starts too late: "
                "for i in range(1, n): print(i, arr[i])",
                "python_execution", [], "loop_fix",
                "for i in range(0, n): print(i, arr[i])",
                fixtures=_prints(lambda v: list(enumerate(v)))),
    # --- SQL (near sql_query); different tables, different questions ---
    TrainPrompt("orders_per_customer",
                "Given a table orders(id, customer, total), write a SQL query returning "
                "each customer and their number of orders, ordered by customer name.",
                "sql_execution", [], "sql",
                "SELECT customer, COUNT(*) FROM orders GROUP BY customer ORDER BY customer;",
                fixtures=(
                    (_ORDERS + _insert("orders", "customer, total",
                                       [("bob", 5), ("alice", 10), ("alice", 20)]),
                     [("alice", 2), ("bob", 1)]),
                    (_ORDERS + _insert("orders", "customer, total", [("cy", 1)]),
                     [("cy", 1)]),
                ),
                sql_functions=frozenset({"count"})),
    TrainPrompt("cheapest_product",
                "Given a table products(id, name, price), write a SQL query that returns "
                "only the name of the cheapest product.",
                "sql_execution", [], "sql",
                "SELECT name FROM products ORDER BY price LIMIT 1;",
                fixtures=(
                    (_PRODUCTS + _insert("products", "name, price",
                                         [("pen", 2), ("book", 12), ("lamp", 30)]),
                     [("pen",)]),
                    (_PRODUCTS + _insert("products", "name, price",
                                         [("desk", 90), ("mug", 8)]),
                     [("mug",)]),
                ),
                sql_functions=frozenset({"min"})),
    TrainPrompt("big_spenders",
                "Given a table orders(id, customer, total), write a SQL query returning "
                "the names of customers whose order totals add up to more than 100, "
                "one column, ordered by name.",
                "sql_execution", [], "sql",
                "SELECT customer FROM orders GROUP BY customer "
                "HAVING SUM(total) > 100 ORDER BY customer;",
                fixtures=(
                    (_ORDERS + _insert("orders", "customer, total",
                                       [("alice", 60), ("alice", 50), ("bob", 90), ("cy", 150)]),
                     [("alice",), ("cy",)]),
                    (_ORDERS + _insert("orders", "customer, total", [("dee", 100)]),
                     []),
                ),
                sql_functions=frozenset({"sum"})),
    # --- systems planning (near multistep_planning) ---
    TrainPrompt("feature_flag_rollout",
                "Plan a 3-step rollout for enabling a risky feature flag for all users, "
                "including how you would detect problems and roll back.",
                "llm_judge", ["canary", "metrics", "percentage", "rollback"], "planning",
                "1) Enable the flag for a small canary cohort and compare error-rate and "
                "latency metrics against control. 2) Ramp the percentage of users in "
                "stages, holding at each step long enough to see regressions. 3) Go to "
                "100% only when metrics hold, keeping the flag as an instant rollback "
                "switch until the old path is deleted."),
    TrainPrompt("mysql_to_postgres",
                "Outline how to migrate a production database from MySQL to PostgreSQL "
                "with minimal downtime.",
                "llm_judge", ["replication", "validation", "cutover", "rollback"], "planning",
                "Set up continuous replication from MySQL into PostgreSQL and backfill "
                "history. Run validation by comparing row counts and checksums, and "
                "shadow read traffic against the new database. Schedule a short cutover: "
                "stop writes, drain replication lag, flip the connection string. Keep "
                "reverse replication running as the rollback path until confidence is high."),
    # --- proofs (near hard_math_proof) ---
    TrainPrompt("infinite_primes", "Prove that there are infinitely many prime numbers.",
                "llm_judge", ["contradiction", "product", "divide", "prime"], "proof",
                "Suppose for contradiction that the primes are finite: p1, ..., pk. Let N "
                "be their product plus 1. Dividing N by any pi leaves remainder 1, so no "
                "pi can divide N. Then N is either prime itself or has a prime factor "
                "missing from the list, contradicting that the list was complete."),
    TrainPrompt("log2_3_irrational", "Show that log base 2 of 3 is irrational.",
                "llm_judge", ["contradiction", "even", "odd", "integers"], "proof",
                "Assume for contradiction that log2(3) = a/b with positive integers a and "
                "b. Then 2^(a/b) = 3, so 2^a = 3^b. The left side is even because a >= 1, "
                "while the right side is a power of 3 and therefore odd. An even number "
                "cannot equal an odd one, so log2(3) is irrational."),
]
