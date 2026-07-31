"""Async Postgres connection pool + schema migration for gatoway.

Usage:
    python -m gatoway.db migrate
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from pgvector.asyncpg import register_vector

load_dotenv()

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register the pgvector codec so list[float] binds to VECTOR columns.

    Without this, asyncpg has no codec for the `vector` type and any query
    passing an embedding as a parameter (e.g. router.py's similarity search)
    fails to bind.
    """
    await register_vector(conn)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and adjust if needed."
        )
    return url


async def get_pool() -> asyncpg.Pool:
    """Return a lazily-created, process-wide connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=_database_url(), init=_init_connection)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def migrate() -> None:
    """Apply schema.sql against DATABASE_URL. Idempotent (uses IF NOT EXISTS)."""
    sql = SCHEMA_PATH.read_text()
    conn = await asyncpg.connect(dsn=_database_url())
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    print(f"Applied {SCHEMA_PATH} to {_database_url()}")


def _main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] != "migrate":
        print("Usage: python -m gatoway.db migrate", file=sys.stderr)
        sys.exit(1)
    asyncio.run(migrate())


if __name__ == "__main__":
    _main()
