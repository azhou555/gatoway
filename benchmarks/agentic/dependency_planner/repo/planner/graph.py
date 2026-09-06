class UnknownDependencyError(ValueError):
    pass


class CycleError(ValueError):
    pass


class DuplicateJobError(ValueError):
    pass


def build_plan(jobs):
    """Return job names in runnable order."""
    return [job["name"] for job in jobs]

