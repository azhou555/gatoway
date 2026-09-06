Implement `build_plan(jobs)` in `planner/graph.py`. Each job is a mapping with
a unique `name` and a `depends_on` list. Return every job name exactly once in
a valid topological order.

Production requirements:

- preserve input order whenever multiple jobs are ready at the same time;
- raise `UnknownDependencyError` if a dependency is not present;
- raise `CycleError` for dependency cycles;
- reject duplicate job names with `DuplicateJobError`;
- do not mutate the input objects.

Keep the exception classes and public function signature intact.

