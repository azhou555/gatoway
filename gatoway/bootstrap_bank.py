"""Populate an isolated bank with measured per-model train outcomes.

Difficulty is 1 - mean(score across all eight primary models), never a manual
label. Incomplete/single-rung prompts retain NULL difficulty. Zero-score
answers are evidence; provider failures are skipped, while scorer failures
abort without fabricating outcomes. Checkpoints resume scored pairs and
stable row IDs prevent duplicate observations on reruns.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, urlunsplit
import uuid

import asyncpg

from gatoway.bank_corpus import TRAIN_PROMPTS, assert_no_eval_overlap, score
from gatoway.code_grader import CodeGrader
from gatoway.db import SCHEMA_PATH, _init_connection
from gatoway.embeddings import embed
from gatoway.providers import MODEL_LADDER, RUNG_BY_NAME, ProviderResponse, call_provider

TIMEOUT_SECONDS = 120
ATTEMPTS = 2
DATABASE_MARKER = "gatoway measured eval bank v1"
ROW_NAMESPACE = uuid.UUID("6b68bfd3-cbfc-473d-b4eb-e266b66cf003")
ROOT = Path(__file__).resolve().parent
INSERT = """
INSERT INTO decision_history
    (routing_id, session_id, model_id, calculated_difficulty,
     calculated_effectiveness, confidence, input_embedding, response_embedding)
VALUES ($1, NULL, $2, $3, $4, $5, $6, $7)
ON CONFLICT (routing_id) DO UPDATE SET
    model_id = EXCLUDED.model_id,
    calculated_difficulty = EXCLUDED.calculated_difficulty,
    calculated_effectiveness = EXCLUDED.calculated_effectiveness,
    confidence = EXCLUDED.confidence,
    input_embedding = EXCLUDED.input_embedding,
    response_embedding = EXCLUDED.response_embedding
"""


def row_id(prompt_id, model_id):
    return uuid.uuid5(ROW_NAMESPACE, f"{prompt_id}/{model_id}")


def validate_database_name(name: str) -> None:
    if not re.fullmatch(r"gatoway_eval_[a-z0-9_]{1,45}", name):
        raise ValueError("database must be named gatoway_eval_<lowercase identifier>")


def source_database_url():
    """Use an explicit DSN or the repository's local Docker Compose defaults."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = quote(os.environ.get("POSTGRES_USER", "gatoway"), safe="")
    password = quote(os.environ.get("POSTGRES_PASSWORD", "gatoway"), safe="")
    database = quote(os.environ.get("POSTGRES_DB", "gatoway"), safe="")
    return f"postgresql://{user}:{password}@localhost:5432/{database}"


async def isolated_pool(name: str):
    """Create/verify only a separately named, marked evaluation database."""
    validate_database_name(name)
    source = source_database_url()
    parts = urlsplit(source)
    if parts.path.lstrip("/") == name:
        raise ValueError("DATABASE_URL must identify the original database, not the target")
    admin = await asyncpg.connect(source)
    try:
        existing = await admin.fetchrow(
            "SELECT shobj_description(oid, 'pg_database') AS marker "
            "FROM pg_database WHERE datname=$1", name
        )
        if existing is None:
            await admin.execute(f'CREATE DATABASE "{name}"')
            await admin.execute(f'COMMENT ON DATABASE "{name}" IS \'{DATABASE_MARKER}\'')
        elif existing["marker"] != DATABASE_MARKER:
            raise ValueError("refusing an existing database without the bootstrap ownership marker")
    finally:
        await admin.close()
    dsn = urlunsplit(parts._replace(path="/" + name))
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(SCHEMA_PATH.read_text())
        expected_ids = [row_id(task.prompt_id, rung.primary)
                        for task in TRAIN_PROMPTS for rung in MODEL_LADDER]
        unrelated = await connection.fetchval(
            "SELECT count(*) FROM decision_history WHERE routing_id <> ALL($1::uuid[])",
            expected_ids,
        )
        if unrelated:
            raise ValueError("isolated bank contains unrelated rows; refusing to modify it")
    finally:
        await connection.close()
    return await asyncpg.create_pool(dsn=dsn, init=_init_connection)


def max_tokens(task):
    return 2048 if task.task_dir is not None else 512


def fingerprint(task):
    data = json.dumps(asdict(task), sort_keys=True, default=str).encode()
    for name in ("bank_corpus.py", "eval.py", "code_grader.py", "judge.py",
                 "providers.py", "rubrics.py", "bootstrap_bank.py"):
        data += (ROOT / name).read_bytes()
    if task.task_dir:
        for path in sorted(task.task_dir.iterdir()):
            if path.is_file():
                data += path.name.encode() + path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def save_state(path: Path, state: dict):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(path)


async def bootstrap(pool, *, prompts=None, rungs=None, dry_run=False,
                    checkpoint: Path | None = None, concurrency=4, grader=None):
    prompts = TRAIN_PROMPTS if prompts is None else prompts
    rungs = MODEL_LADDER if rungs is None else rungs
    if not 1 <= concurrency <= 8:
        raise ValueError("concurrency must be between 1 and 8")
    if not prompts or not rungs:
        raise ValueError("prompts and rungs must be nonempty")
    if len({p.prompt_id for p in prompts}) != len(prompts):
        raise ValueError("prompt IDs must be unique")
    assert_no_eval_overlap(prompts)
    summary = {"dry_run": dry_run, "scored": 0, "written": 0,
               "provider_failures": [], "prompts": []}
    semaphore = asyncio.Semaphore(concurrency)
    grader = grader or CodeGrader()
    if checkpoint is not None and not dry_run:
        checkpoint.mkdir(parents=True, exist_ok=True)

    for index, task in enumerate(prompts, 1):
        print(f"[{index}/{len(prompts)}] {task.prompt_id}", flush=True)
        if dry_run:
            for rung in rungs:
                await score(task, task.reference_response, f"dry-run/{rung.name}",
                            dry_run=True, grader=grader)
                summary["scored"] += 1
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", task.prompt_id):
            raise ValueError("unsafe checkpoint prompt ID")
        path = checkpoint / f"{task.prompt_id}.json" if checkpoint else None
        state = {"prompt_id": task.prompt_id, "fingerprint": fingerprint(task), "outcomes": {}}
        if path and path.exists():
            loaded = json.loads(path.read_text())
            if loaded["fingerprint"] != state["fingerprint"]:
                raise ValueError(f"checkpoint differs from current task/scorer: {task.prompt_id}")
            state = loaded

        async def observe(rung):
            if rung.primary in state["outcomes"]:
                return
            async with semaphore:
                state.setdefault("responses", {})
                if rung.primary in state["responses"]:
                    response = ProviderResponse(**state["responses"][rung.primary], raw=None)
                else:
                    for attempt in range(ATTEMPTS):
                        try:
                            response = await asyncio.wait_for(
                                call_provider(rung.primary, [{"role": "user", "content": task.prompt}],
                                              temperature=0, max_tokens=max_tokens(task)),
                                timeout=TIMEOUT_SECONDS,
                            )
                            break
                        except Exception as exc:
                            if attempt + 1 == ATTEMPTS:
                                failure = {"prompt_id": task.prompt_id, "model_id": rung.primary,
                                           "error_type": type(exc).__name__}
                                summary["provider_failures"].append(failure)
                                print(f"  {rung.name}: skipped ({type(exc).__name__})", flush=True)
                                return
                    state["responses"][rung.primary] = {
                        "content": response.content, "model_id": response.model_id,
                        "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                        "cost_cents": response.cost_cents, "finish_reason": response.finish_reason,
                    }
                    if path:
                        save_state(path, state)
                if response.model_id != rung.primary:
                    raise ValueError("bootstrap must observe the requested primary model")
                value = await score(task, response.content, response.model_id, grader=grader)
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError("scorer returned an invalid effectiveness")
                state["outcomes"][rung.primary] = {
                    "score": value, "response": response.content,
                    "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                    "cost_cents": response.cost_cents, "finish_reason": response.finish_reason,
                }
                if path:
                    save_state(path, state)
                print(f"  {rung.name}: {value:.3f}", flush=True)

        pending = [asyncio.create_task(observe(rung)) for rung in rungs]
        try:
            await asyncio.gather(*pending)
        except BaseException:
            for future in pending:
                future.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
        all_models = {rung.primary for rung in MODEL_LADDER}
        outcomes = state["outcomes"]
        difficulty = (1 - sum(outcomes[model]["score"] for model in all_models) / len(all_models)
                      if all_models <= outcomes.keys() else None)
        # A prompt is committed atomically after scoring. Resuming updates these
        # same IDs so repeated CLI invocations cannot inflate neighbor counts.
        vector = embed(task.prompt)
        rows = [(row_id(task.prompt_id, model), model, difficulty, observation["score"],
                 1.0, vector, embed(observation["response"]))
                for model, observation in outcomes.items()]
        async with pool.acquire() as connection:
            async with connection.transaction():
                for row in rows:
                    await connection.execute(INSERT, *row)
        summary["scored"] += len(rows)
        summary["written"] += len(rows)
        summary["prompts"].append({"prompt_id": task.prompt_id, "rows": len(rows),
                                   "difficulty": difficulty,
                                   "scores": {m: o["score"] for m, o in outcomes.items()}})
        if checkpoint:
            save_state(checkpoint / "summary.json", summary)
    return summary


async def main(args):
    if args.dry_run:
        result = await bootstrap(None, dry_run=True,
                                 rungs=[RUNG_BY_NAME[args.rung]] if args.rung else None)
    else:
        if not args.database:
            raise ValueError("--database gatoway_eval_<name> is required for live bootstrap")
        validate_database_name(args.database)
        grader = CodeGrader()
        for language in ("python", "typescript"):
            grader.preflight(language)
        pool = await isolated_pool(args.database)
        try:
            checkpoint = args.checkpoint or Path("artifacts") / args.database
            result = await bootstrap(
                pool, rungs=[RUNG_BY_NAME[args.rung]] if args.rung else None,
                checkpoint=checkpoint, concurrency=args.concurrency, grader=grader,
            )
        finally:
            await pool.close()
    print(json.dumps({key: value for key, value in result.items() if key != "prompts"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rung", choices=RUNG_BY_NAME)
    parser.add_argument("--database")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--concurrency", type=int, default=4)
    asyncio.run(main(parser.parse_args()))
