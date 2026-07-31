"""Gateway latency benchmark (SPEC.md §9).

SPEC.md §9: "Target: <=100ms added by the gateway on top of native provider
latency (embedding lookup + routing logic). Provider call latency itself is
out of the gateway's control and excluded from this budget."

This measures exactly that: a full POST /v1/chat/completions request through
the real app -- real local embedding model, real live Postgres (session
tracker read/write, router nearest-neighbor query, decision_history insert)
-- with only the provider network call itself replaced by an instant stand-in
(litellm/Anthropic latency is explicitly out of scope for this budget, and
substituting it here keeps the benchmark free to run, no API key needed).

Usage:
    python -m gatoway.bench_latency [N]   # N requests, default 30
"""

from __future__ import annotations

import statistics
import sys
import time
import uuid

from fastapi.testclient import TestClient

import gatoway.app as app_module
from gatoway.providers import ProviderResponse

TARGET_MS = 100.0


def _instant_response(model_id: str) -> ProviderResponse:
    return ProviderResponse(
        content="ok",
        model_id=model_id,
        input_tokens=5,
        output_tokens=1,
        cost_cents=0.0,
        raw=None,
    )


async def _instant_breaker_call(self, tier, messages, **kwargs):
    return _instant_response(f"instant-stub/{tier}")


async def _instant_classifier_fallback(messages, **kwargs):
    return _instant_response("instant-stub/medium")


PROMPTS = [
    "What is the capital of France?",
    "Fix the off-by-one bug in this loop.",
    "Plan a 3-step migration strategy considering data consistency risks.",
    "What is 12 * 34?",
    "Explain the tradeoffs between REST and GraphQL.",
]


def run(n: int) -> list[float]:
    app_module.CircuitBreaker.call = _instant_breaker_call
    app_module.call_with_classifier_fallback = _instant_classifier_fallback

    latencies_ms: list[float] = []

    # `with` keeps a single event loop/portal alive for the whole client
    # lifetime -- without it, TestClient spins a fresh loop per request and
    # the asyncpg pool (opened lazily on the first request) ends up attached
    # to a stale loop on the second one.
    with TestClient(app_module.app) as client:
        # Warmup: loads the embedding model and opens the DB pool, both
        # one-time costs that shouldn't count against per-request latency.
        client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "warmup"}], "session_id": str(uuid.uuid4())},
        )

        for i in range(n):
            prompt = PROMPTS[i % len(PROMPTS)]
            start = time.perf_counter()
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "session_id": str(uuid.uuid4()),  # each request its own session: measures start_session's cost, the common case
                },
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            if resp.status_code != 200:
                print(f"  [warn] request {i} returned {resp.status_code}: {resp.text}")
                continue
            latencies_ms.append(elapsed_ms)

    return latencies_ms


def _pctile(data: list[float], p: float) -> float:
    data = sorted(data)
    k = (len(data) - 1) * p
    f, c = int(k), min(int(k) + 1, len(data) - 1)
    return data[f] + (data[c] - data[f]) * (k - f)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(f"Running {n} requests through the real gateway pipeline "
          f"(real embedding model + live Postgres; provider call stubbed "
          f"to be instant, per SPEC.md §9's exclusion)...\n")

    latencies_ms = run(n)
    if not latencies_ms:
        print("No successful requests -- can't report latency.")
        sys.exit(1)

    p50, p95, p99 = _pctile(latencies_ms, 0.50), _pctile(latencies_ms, 0.95), _pctile(latencies_ms, 0.99)
    mean = statistics.mean(latencies_ms)

    print(f"n={len(latencies_ms)}  mean={mean:.1f}ms  p50={p50:.1f}ms  "
          f"p95={p95:.1f}ms  p99={p99:.1f}ms  max={max(latencies_ms):.1f}ms")
    print(f"SPEC.md §9 target: <={TARGET_MS:.0f}ms gateway overhead\n")

    verdict = "PASS" if p95 <= TARGET_MS else "FAIL"
    print(f"-> {verdict}: p95 {'<=' if verdict == 'PASS' else '>'} {TARGET_MS:.0f}ms target")


if __name__ == "__main__":
    main()
