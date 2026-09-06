The in-memory `TTLCache` has incorrect expiration semantics and an incomplete
loader API. Fix it so that:

- entries expire when their age is greater than or equal to the configured TTL;
- a TTL less than or equal to zero disables caching;
- expired entries are removed;
- `get_or_load(key, loader)` invokes `loader` exactly once on a miss and can
  cache `None` as a legitimate value.

Keep the public constructor, `put`, `get`, and `get_or_load` signatures intact.

