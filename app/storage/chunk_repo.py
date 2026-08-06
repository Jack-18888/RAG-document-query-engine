from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.storage import db


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    chunk_index: int
    text: str
    tokens: int


def _row_to_chunk(row: Any) -> Chunk:
    return Chunk(
        id=row["id"],
        doc_id=row["doc_id"],
        chunk_index=row["chunk_index"],
        text=row["text"],
        tokens=row["tokens"],
    )


async def insert_many(chunks: list[Chunk]) -> None:
    conn = db.get_connection()
    await conn.executemany(
        "INSERT INTO chunks (id, doc_id, chunk_index, text, tokens) VALUES (?, ?, ?, ?, ?)",
        [(c.id, c.doc_id, c.chunk_index, c.text, c.tokens) for c in chunks],
    )
    await conn.commit()


async def count_by_document(doc_id: str) -> int:
    conn = db.get_connection()
    async with conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)) as cursor:
        row = await cursor.fetchone()
    return int(row[0])


async def list_by_document(doc_id: str) -> list[Chunk]:
    conn = db.get_connection()
    async with conn.execute(
        "SELECT id, doc_id, chunk_index, text, tokens FROM chunks "
        "WHERE doc_id = ? ORDER BY chunk_index",
        (doc_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_chunk(row) for row in rows]


async def delete_by_document(doc_id: str) -> None:
    conn = db.get_connection()
    await conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    await conn.commit()
