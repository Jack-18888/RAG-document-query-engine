from __future__ import annotations

import re

from app.storage import db

_WHITESPACE = re.compile(r"\s+")


def _fts_query(text: str) -> str | None:
    terms = _WHITESPACE.split(text.strip())
    terms = [term for term in terms if term]
    if not terms:
        return None
    return " ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


async def search(text: str, k: int = 10) -> list[str]:
    query = _fts_query(text)
    if query is None:
        return []

    conn = db.get_connection()
    async with conn.execute(
        "SELECT c.id FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid "
        "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
        (query, k),
    ) as cursor:
        rows = await cursor.fetchall()
    return [row[0] for row in rows]
