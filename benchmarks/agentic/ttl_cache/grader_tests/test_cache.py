import unittest

from cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class TTLCacheTests(unittest.TestCase):
    def test_value_expires_at_exact_boundary_and_is_removed(self):
        clock = Clock()
        cache = TTLCache(10, clock)
        cache.put("key", "value")
        clock.now += 10
        self.assertIsNone(cache.get("key"))
        self.assertNotIn("key", cache._values)

    def test_non_positive_ttl_disables_caching(self):
        for ttl in (0, -1):
            clock = Clock()
            cache = TTLCache(ttl, clock)
            cache.put("key", "value")
            self.assertIsNone(cache.get("key"))
            self.assertNotIn("key", cache._values)

    def test_loader_runs_once_and_none_is_cached(self):
        clock = Clock()
        cache = TTLCache(10, clock)
        calls = []

        def load():
            calls.append(1)
            return None

        self.assertIsNone(cache.get_or_load("key", load))
        self.assertIsNone(cache.get_or_load("key", load))
        self.assertEqual(len(calls), 1)

    def test_loader_result_is_cached_until_expiration(self):
        clock = Clock()
        cache = TTLCache(5, clock)
        calls = []

        def load():
            calls.append(1)
            return len(calls)

        self.assertEqual(cache.get_or_load("key", load), 1)
        self.assertEqual(cache.get_or_load("key", load), 1)
        clock.now += 5
        self.assertEqual(cache.get_or_load("key", load), 2)


if __name__ == "__main__":
    unittest.main()

