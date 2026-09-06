_MISSING = object()


class TTLCache:
    def __init__(self, ttl_seconds, clock):
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._values = {}

    def put(self, key, value):
        self._values[key] = (value, self._clock())

    def get(self, key):
        item = self._values.get(key, _MISSING)
        if item is _MISSING:
            return None

        value, inserted_at = item
        if self._clock() - inserted_at > self.ttl_seconds:
            return None
        return value

    def get_or_load(self, key, loader):
        value = self.get(key)
        if value is not None:
            return value
        return loader()

