import copy
import unittest

from planner import CycleError, DuplicateJobError, UnknownDependencyError, build_plan


class PlannerTests(unittest.TestCase):
    def test_dependencies_precede_consumers(self):
        jobs = [
            {"name": "deploy", "depends_on": ["build", "lint"]},
            {"name": "lint", "depends_on": []},
            {"name": "build", "depends_on": []},
        ]
        self.assertEqual(build_plan(jobs), ["lint", "build", "deploy"])

    def test_newly_ready_jobs_keep_input_order(self):
        jobs = [
            {"name": "api", "depends_on": ["db"]},
            {"name": "worker", "depends_on": ["db"]},
            {"name": "db", "depends_on": []},
        ]
        self.assertEqual(build_plan(jobs), ["db", "api", "worker"])

    def test_unknown_dependency(self):
        with self.assertRaises(UnknownDependencyError):
            build_plan([{"name": "api", "depends_on": ["missing"]}])

    def test_cycle(self):
        with self.assertRaises(CycleError):
            build_plan([
                {"name": "a", "depends_on": ["b"]},
                {"name": "b", "depends_on": ["a"]},
            ])

    def test_duplicate_name(self):
        with self.assertRaises(DuplicateJobError):
            build_plan([
                {"name": "a", "depends_on": []},
                {"name": "a", "depends_on": []},
            ])

    def test_input_is_not_mutated(self):
        jobs = [
            {"name": "b", "depends_on": ["a"]},
            {"name": "a", "depends_on": []},
        ]
        original = copy.deepcopy(jobs)
        build_plan(jobs)
        self.assertEqual(jobs, original)


if __name__ == "__main__":
    unittest.main()

