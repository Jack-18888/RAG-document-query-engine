"""SQLite connection lifecycle and schema initialization."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from app.config import get_settings

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data/db_init.sql"

_connection: aiosqlite.Connection | None = None


def _database_path(path: str | None) -> str:
    """Resolve the database path, falling back to settings."""
    if path is not None:
        return path
    return get_settings().database_path


async def init_db(path: str | None = None) -> None:
    """Create the database schema if it does not exist yet."""
    db_path = _database_path(path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        await conn.commit()


async def connect(path: str | None = None) -> aiosqlite.Connection:
    """Open a new connection with row-factory enabled, creating parent dirs."""
    db_path = _database_path(path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    return conn


async def open_database(path: str | None = None) -> None:
    """Initialize the schema and store the shared app connection."""
    global _connection
    await init_db(path)
    _connection = await connect(path)


async def close_database() -> None:
    """Close the shared app connection, if open."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None


def get_connection() -> aiosqlite.Connection:
    """Return the shared app connection.

    Raises :class:`RuntimeError` if :func:`open_database` has not been called.
    """
    if _connection is None:
        raise RuntimeError("database is not initialized; call open_database() first")
    return _connection
