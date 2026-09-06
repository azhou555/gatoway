import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from delivery import WebhookProcessor


class WebhookProcessorTests(unittest.TestCase):
    def test_success_is_idempotent(self):
        processor = WebhookProcessor()
        calls = []

        def handler(payload):
            calls.append(payload)
            return "accepted"

        self.assertEqual(processor.process("evt-1", {}, handler), "accepted")
        self.assertEqual(processor.process("evt-1", {}, handler), "accepted")
        self.assertEqual(len(calls), 1)

    def test_concurrent_duplicate_runs_once(self):
        processor = WebhookProcessor()
        calls = 0
        calls_lock = threading.Lock()
        release = threading.Event()

        def handler(payload):
            nonlocal calls
            with calls_lock:
                calls += 1
            release.wait(timeout=2)
            return payload["value"]

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(processor.process, "evt-2", {"value": 42}, handler)
                for _ in range(8)
            ]
            time.sleep(0.05)
            release.set()
            self.assertEqual([future.result(timeout=2) for future in futures], [42] * 8)
        self.assertEqual(calls, 1)

    def test_failure_can_be_retried(self):
        processor = WebhookProcessor()
        attempts = 0

        def handler(payload):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary failure")
            return "ok"

        with self.assertRaises(RuntimeError):
            processor.process("evt-3", {}, handler)
        self.assertEqual(processor.process("evt-3", {}, handler), "ok")
        self.assertEqual(attempts, 2)

    def test_different_events_are_not_serialized(self):
        processor = WebhookProcessor()
        barrier = threading.Barrier(2, timeout=2)

        def handler(payload):
            barrier.wait()
            return payload

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(processor.process, "evt-a", "a", handler)
            second = executor.submit(processor.process, "evt-b", "b", handler)
            self.assertEqual({first.result(timeout=2), second.result(timeout=2)}, {"a", "b"})


if __name__ == "__main__":
    unittest.main()

