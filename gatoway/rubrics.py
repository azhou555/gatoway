"""Concrete criteria for the original open-ended benchmark neighborhoods."""

RUBRICS = {
    "multistep_planning": [
        "Extracts one bounded context incrementally behind a compatibility boundary.",
        "Explains how an outbox or equivalent avoids unsafe dual writes.",
        "Validates data consistency before switching to the new data store.",
        "Gives a rollback path and staged cutover.",
    ],
    "hard_math_proof": [
        "Assumes sqrt(2)=a/b in lowest terms for a contradiction.",
        "Derives a squared equals twice b squared, so a must be even.",
        "Substitutes a=2k to show b must also be even.",
        "Contradicts coprimality of a and b and concludes irrationality.",
    ],
    "shared_database_split": [
        "Assigns ownership and one writer per entity to prevent contention.",
        "Backfills new stores before cutting over.",
        "Uses an outbox or equivalent to avoid unsafe dual writes.",
        "Validates consistency and preserves a rollback route.",
    ],
    "database_column_rollout": [
        "Adds the new column while retaining compatibility with old binaries.",
        "Maintains both columns during the transition.",
        "Backfills existing rows and validates equality before switching reads.",
        "Defers dropping the old column until old binaries retire and rollback is safe.",
    ],
    "infinitely_many_primes": [
        "Assumes a finite complete list of primes for contradiction.",
        "Constructs the product of all listed primes plus one.",
        "Shows no listed prime divides the constructed integer.",
        "Uses existence of a prime divisor to contradict completeness.",
    ],
    "sum_first_odd_numbers": [
        "Checks the base case n=1.",
        "States the induction hypothesis for the first n odd integers.",
        "Identifies the next term as 2n+1.",
        "Derives n squared plus 2n+1 equals (n+1) squared and concludes induction.",
    ],
}
