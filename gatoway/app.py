"""Gateway API (SPEC.md §3 "Gateway API", TASKS.md Subtask 4).

OpenAI-compatible `POST /v1/chat/completions` that wires together the pieces
built in earlier subtasks:

    SessionTracker -> router.classify() -> CircuitBreaker.call()
        -> decision_history write

Per SPEC.md §5's fallback state machine:
- `classify()` raising (embedding/DB error) -> `call_with_classifier_fallback`
  (medium tier, single request, bypasses the breaker entirely).
- `classify()` succeeding -> the chosen tier is called through the
  `CircuitBreaker`, which itself retries once with a different provider in
  the tier and trips a 60s cooldown after 3 consecutive failures
  (`TierInCooldownError`).
- If every avenue is exhausted, the endpoint returns a 503 in an
  OpenAI-compatible error shape instead of crashing.

No auth/rate-limiting/DI framework -- explicitly out of scope per SPEC.md
non-goals and TASKS.md's MVP cut list.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gatoway.circuit_breaker import (
    CircuitBreaker,
    TierInCooldownError,
    call_with_classifier_fallback,
)
from gatoway.db import close_pool, get_pool
from gatoway.embeddings import embed
from gatoway.providers import ProviderResponse
from gatoway.router import classify
from gatoway.session import SessionTracker

logger = logging.getLogger("gatoway")

# Placeholder team_id used when a request doesn't supply one. Auth/team
# resolution is out of scope for the MVP (SPEC.md non-goals).
DEFAULT_TEAM_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# Single process-wide breaker instance: circuit state is meant to persist
# across requests (that's the whole point of the cooldown), per
# gatoway/circuit_breaker.py's "in-process state is fine for MVP" note.
breaker = CircuitBreaker()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    await close_pool()


app = FastAPI(title="gatoway", version="0.1.0", lifespan=_lifespan)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage]
    session_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    model: str | None = None  # accepted for OpenAI-shape compat, unused: gatoway picks the model
    extra: dict[str, Any] = Field(default_factory=dict)


def _last_user_text(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    # Fall back to the last message of any role if no "user" turn is present.
    return messages[-1].content


def _error_response(status_code: int, message: str, error_type: str) -> JSONResponse:
    """OpenAI-compatible error shape."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "code": status_code}},
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> JSONResponse:
    start = time.monotonic()
    pool = await get_pool()

    session_id = request.session_id or uuid.uuid4()
    team_id = request.team_id or DEFAULT_TEAM_ID
    is_new_session = request.session_id is None
    messages = [m.model_dump() for m in request.messages]
    input_text = _last_user_text(request.messages)

    tracker = SessionTracker(pool)
    if is_new_session:
        turn = await tracker.start_session(session_id, team_id, input_text)
    else:
        try:
            turn = await tracker.process_turn(session_id, input_text)
        except ValueError:
            # Client supplied a session_id we've never seen -- treat it as
            # the start of a new (client-named) session rather than 500ing.
            turn = await tracker.start_session(session_id, team_id, input_text)

    classifier_failed = False
    try:
        decision = await classify(input_text, pool, turn.current_threshold)
        tier = decision.tier
        confidence = decision.confidence
        calculated_difficulty = decision.calculated_difficulty
        input_embedding = decision.input_embedding
    except Exception as exc:  # noqa: BLE001 - classifier errors are opaque by contract
        logger.warning("classifier failed, falling back to medium tier: %s", exc)
        classifier_failed = True
        tier = "medium"
        confidence = None
        calculated_difficulty = None
        input_embedding = embed(input_text)

    provider_error: str | None = None
    response: ProviderResponse | None = None
    try:
        if classifier_failed:
            response = await call_with_classifier_fallback(messages)
        else:
            response = await breaker.call(tier, messages)
    except TierInCooldownError as exc:
        provider_error = f"tier '{exc.tier}' is temporarily unavailable (cooldown for {exc.retry_after:.0f}s more)"
    except Exception as exc:  # noqa: BLE001 - provider/breaker errors are opaque
        provider_error = f"all providers for tier '{tier}' failed: {exc}"

    latency_ms = (time.monotonic() - start) * 1000

    if response is None:
        logger.error(
            "request failed session=%s tier=%s classifier_failed=%s error=%s latency_ms=%.1f",
            session_id, tier, classifier_failed, provider_error, latency_ms,
        )
        return _error_response(503, provider_error or "provider call failed", "provider_error")

    routing_id = uuid.uuid4()
    response_embedding = embed(response.content)
    await pool.execute(
        """
        INSERT INTO decision_history
            (routing_id, session_id, model_id, calculated_difficulty, confidence,
             input_embedding, response_embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        routing_id, session_id, response.model_id, calculated_difficulty, confidence,
        input_embedding, response_embedding,
    )

    logger.info(
        "request ok session=%s tier=%s model=%s classifier_failed=%s confidence=%s "
        "cost_cents=%.4f latency_ms=%.1f",
        session_id, tier, response.model_id, classifier_failed, confidence,
        response.cost_cents, latency_ms,
    )

    body = {
        "id": str(routing_id),
        "object": "chat.completion",
        "model": response.model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response.content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": response.input_tokens,
            "completion_tokens": response.output_tokens,
            "total_tokens": response.input_tokens + response.output_tokens,
        },
        "gatoway": {
            "session_id": str(session_id),
            "team_id": str(team_id),
            "tier": tier,
            "model_id": response.model_id,
            "classifier_failed": classifier_failed,
            "confidence": confidence,
            "calculated_difficulty": calculated_difficulty,
            "cost_cents": response.cost_cents,
            "turn_count": turn.turn_count,
            "current_threshold": turn.current_threshold,
            "latency_ms": round(latency_ms, 1),
        },
    }
    return JSONResponse(status_code=200, content=body)
