import sqlite3
from types import SimpleNamespace

import aiosqlite
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import db


async def _columns(conn: aiosqlite.Connection, table: str) -> set[str]:
    rows = await conn.execute_fetchall(f"PRAGMA table_info({table})")
    return {row[1] for row in rows}


async def test_init_db_creates_tables_and_fts(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    await db.init_db(str(db_path))

    async with aiosqlite.connect(db_path) as conn:
        tables = {
            row[0]
            for row in await conn.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        triggers = {
            row[0]
            for row in await conn.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }

    assert {"documents", "chunks", "jobs", "chunks_fts"} <= tables
    assert {"chunks_auto_insert", "chunks_auto_delete", "chunks_auto_update"} <= triggers


async def test_init_db_creates_expected_columns(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    await db.init_db(str(db_path))

    async with aiosqlite.connect(db_path) as conn:
        assert await _columns(conn, "documents") == {
            "id",
            "name",
            "format",
            "size_bytes",
            "status",
            "error_message",
            "created_at",
            "updated_at",
        }
        assert await _columns(conn, "chunks") == {
            "id",
            "doc_id",
            "chunk_index",
            "text",
            "tokens",
        }
        assert await _columns(conn, "jobs") == {
            "id",
            "document_id",
            "stage",
            "chunks_processed",
            "chunks_total",
            "error_message",
            "created_at",
            "updated_at",
        }


async def test_init_db_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    await db.init_db(str(db_path))
    await db.init_db(str(db_path))

    async with aiosqlite.connect(db_path) as conn:
        counts = await conn.execute_fetchall(
            "SELECT name, count(*) FROM sqlite_master "
            "WHERE type='table' AND name IN ('documents', 'chunks', 'jobs', 'chunks_fts') "
            "GROUP BY name"
        )
    assert {row[0] for row in counts} == {"documents", "chunks", "jobs", "chunks_fts"}
    assert all(row[1] == 1 for row in counts)


async def test_chunk_insert_and_delete_sync_fts(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    await db.init_db(str(db_path))

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO documents (id, name, format, size_bytes) VALUES (?, ?, ?, ?)",
            ("doc_1", "notes.md", "md", 12),
        )
        await conn.execute(
            "INSERT INTO chunks (id, doc_id, chunk_index, text, tokens) VALUES (?, ?, ?, ?, ?)",
            ("chunk_1", "doc_1", 0, "alpha beta gamma", 3),
        )
        await conn.commit()

        hits = await conn.execute_fetchall(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alpha'"
        )
        assert sum(1 for _ in hits) == 1

        await conn.execute("DELETE FROM chunks WHERE id = 'chunk_1'")
        await conn.commit()

        hits = await conn.execute_fetchall(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alpha'"
        )
        assert hits == []


async def test_bm25_ranking_over_chunks(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    await db.init_db(str(db_path))

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO documents (id, name, format, size_bytes) VALUES (?, ?, ?, ?)",
            ("doc_1", "notes.md", "md", 12),
        )
        await conn.executemany(
            "INSERT INTO chunks (id, doc_id, chunk_index, text, tokens) VALUES (?, ?, ?, ?, ?)",
            [
                ("chunk_1", "doc_1", 0, "the quick brown fox", 4),
                ("chunk_2", "doc_1", 1, "nothing to see here", 4),
                ("chunk_3", "doc_1", 2, "fox fox fox fox", 4),
            ],
        )
        await conn.commit()

        rows = await conn.execute_fetchall(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'fox' "
            "ORDER BY bm25(chunks_fts) LIMIT 10"
        )
    assert sum(1 for _ in rows) == 2


async def test_database_path_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.storage.db.get_settings",
        lambda: SimpleNamespace(database_path="data/engine.db"),
    )
    assert db._database_path(None) == "data/engine.db"
    assert db._database_path("tmp/custom.db") == "tmp/custom.db"


async def test_open_close_database(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    try:
        await db.open_database(str(db_path))
        assert db.get_connection() is not None
    finally:
        await db.close_database()
    try:
        db.get_connection()
    except RuntimeError:
        pass
    else:
        raise AssertionError("get_connection() should raise after close_database()")


def test_lifespan_initializes_database(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "data" / "engine.db"
    monkeypatch.setattr(
        "app.storage.db.get_settings",
        lambda: SimpleNamespace(database_path=str(db_path)),
    )

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"documents", "chunks", "jobs", "chunks_fts"} <= tables
