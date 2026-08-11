"""SQLite repository for queries and their fetched chunks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.storage import db


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_id() -> str:
    """Return a new unique query id."""
    return f"query_{uuid.uuid4().hex[:12]}"


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an aiosqlite query row into a plain dict."""
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "created_at": row["created_at"],
    }


async def create(question: str, answer: str, sources: list[tuple[str, float]]) -> dict[str, Any]:
    """Insert a query row and its fetched chunks, returning the query record.

    ``sources`` is a list of ``(chunk_id, score)`` pairs in citation order.
    """
    conn = db.get_connection()
    query_id = _generate_id()
    now = _utc_now_iso()
    await conn.execute(
        "INSERT INTO queries (id, question, answer, created_at) VALUES (?, ?, ?, ?)",
        (query_id, question, answer, now),
    )
    if sources:
        await conn.executemany(
            "INSERT INTO query_chunks (query_id, chunk_id, score) VALUES (?, ?, ?)",
            [(query_id, chunk_id, score) for chunk_id, score in sources],
        )
    await conn.commit()
    return {"id": query_id, "question": question, "answer": answer, "created_at": now}


async def list_all() -> list[dict[str, Any]]:
    """Return all queries, newest first."""
    conn = db.get_connection()
    async with conn.execute(
        "SELECT id, question, answer, created_at FROM queries ORDER BY created_at DESC, rowid DESC"
    ) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_dict(row) for row in rows]


async def get(query_id: str) -> dict[str, Any] | None:
    """Return the query record, or None if it does not exist."""
    conn = db.get_connection()
    async with conn.execute(
        "SELECT id, question, answer, created_at FROM queries WHERE id = ?",
        (query_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


async def get_sources(query_id: str) -> list[dict[str, Any]]:
    """Return the cited chunks for a query in citation order.

    Reconstructs doc metadata and the chunk excerpt by joining against the
    chunks and documents tables, so deleted chunks simply drop out.
    """
    conn = db.get_connection()
    async with conn.execute(
        "SELECT qc.chunk_id, c.doc_id, d.name AS doc_name, c.text AS excerpt, qc.score "
        "FROM query_chunks qc "
        "JOIN chunks c ON c.id = qc.chunk_id "
        "JOIN documents d ON d.id = c.doc_id "
        "WHERE qc.query_id = ? ORDER BY qc.rowid",
        (query_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [
        {
            "chunk_id": row["chunk_id"],
            "doc_id": row["doc_id"],
            "doc_name": row["doc_name"],
            "excerpt": row["excerpt"],
            "score": row["score"],
        }
        for row in rows
    ]


async def delete(query_id: str) -> bool:
    """Delete the query and its fetched-chunk relations, returning whether a
    query row was removed."""
    conn = db.get_connection()
    await conn.execute("DELETE FROM query_chunks WHERE query_id = ?", (query_id,))
    cursor = await conn.execute("DELETE FROM queries WHERE id = ?", (query_id,))
    await conn.commit()
    return cursor.rowcount > 0
