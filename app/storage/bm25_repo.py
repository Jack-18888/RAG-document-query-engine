"""BM25 keyword search over the SQLite FTS5 index."""

from __future__ import annotations

import re

from app.storage import db

_WHITESPACE = re.compile(r"\s+")


def _fts_query(text: str) -> str | None:
    """Build an FTS5 MATCH query from ``text``, or None if it has no terms.

    Each whitespace-separated term is double-quoted (with embedded quotes
    escaped) so it is matched as a literal phrase rather than parsed syntax.
    """
    terms = _WHITESPACE.split(text.strip())
    terms = [term for term in terms if term]
    if not terms:
        return None
    return " ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


async def search(text: str, k: int = 10) -> list[str]:
    """Return the top ``k`` chunk ids ranked by BM25 relevance for ``text``."""
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
