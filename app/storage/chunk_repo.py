"""SQLite repository for document chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.storage import db


@dataclass(frozen=True)
class Chunk:
    """An indexed chunk of a document."""

    id: str
    doc_id: str
    chunk_index: int
    text: str
    tokens: int


def _row_to_chunk(row: Any) -> Chunk:
    """Convert an aiosqlite row into a :class:`Chunk`."""
    return Chunk(
        id=row["id"],
        doc_id=row["doc_id"],
        chunk_index=row["chunk_index"],
        text=row["text"],
        tokens=row["tokens"],
    )


async def insert_many(chunks: list[Chunk]) -> None:
    """Insert multiple chunks in one transaction."""
    conn = db.get_connection()
    await conn.executemany(
        "INSERT INTO chunks (id, doc_id, chunk_index, text, tokens) VALUES (?, ?, ?, ?, ?)",
        [(c.id, c.doc_id, c.chunk_index, c.text, c.tokens) for c in chunks],
    )
    await conn.commit()


async def count_by_document(doc_id: str) -> int:
    """Count the chunks indexed for a document."""
    conn = db.get_connection()
    async with conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)) as cursor:
        row = await cursor.fetchone()
    if row:
        return int(row[0])
    return 0


async def list_by_document(doc_id: str) -> list[Chunk]:
    """Return all chunks of a document in index order."""
    conn = db.get_connection()
    async with conn.execute(
        "SELECT id, doc_id, chunk_index, text, tokens FROM chunks "
        "WHERE doc_id = ? ORDER BY chunk_index",
        (doc_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_chunk(row) for row in rows]


async def get_by_ids(chunk_ids: list[str]) -> list[Chunk]:
    """Fetch chunks by id, preserving the order of ``chunk_ids``."""
    if not chunk_ids:
        return []
    conn = db.get_connection()
    placeholders = ",".join("?" for _ in chunk_ids)
    async with conn.execute(
        f"SELECT id, doc_id, chunk_index, text, tokens FROM chunks WHERE id IN ({placeholders})",
        chunk_ids,
    ) as cursor:
        rows = await cursor.fetchall()
    by_id = {row["id"]: _row_to_chunk(row) for row in rows}
    return [by_id[cid] for cid in chunk_ids if cid in by_id]


async def delete_by_document(doc_id: str) -> None:
    """Delete all chunks belonging to a document."""
    conn = db.get_connection()
    await conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    await conn.commit()
