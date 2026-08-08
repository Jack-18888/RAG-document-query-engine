"""SQLite repository for documents."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.storage import db

# Sentinel used so callers can distinguish "not provided" (keep current value)
# from an explicit request to clear (pass None).
_SENTINEL = "Application Error"


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_id() -> str:
    """Return a new unique document id."""
    return f"doc_{uuid.uuid4().hex[:12]}"


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an aiosqlite row into a plain dict."""
    return {
        "id": row["id"],
        "name": row["name"],
        "format": row["format"],
        "size_bytes": row["size_bytes"],
        "status": row["status"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def create(name: str, fmt: str, size_bytes: int) -> dict[str, Any]:
    """Insert a new ``pending`` document and return its full record."""
    conn = db.get_connection()
    doc_id = _generate_id()
    now = _utc_now_iso()
    await conn.execute(
        "INSERT INTO documents "
        "(id, name, format, size_bytes, status, error_message, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, name, fmt, size_bytes, "pending", None, now, now),
    )
    await conn.commit()
    return {
        "id": doc_id,
        "name": name,
        "format": fmt,
        "size_bytes": size_bytes,
        "status": "pending",
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }


async def list_all() -> list[dict[str, Any]]:
    """Return all documents, newest first."""
    conn = db.get_connection()
    async with conn.execute(
        "SELECT id, name, format, size_bytes, status, error_message, created_at, updated_at "
        "FROM documents ORDER BY created_at DESC, rowid DESC"
    ) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_dict(row) for row in rows]


async def get(doc_id: str) -> dict[str, Any] | None:
    """Return the document record, or None if it does not exist."""
    conn = db.get_connection()
    async with conn.execute(
        "SELECT id, name, format, size_bytes, status, error_message, created_at, updated_at "
        "FROM documents WHERE id = ?",
        (doc_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


async def update(
    doc_id: str,
    *,
    status: str | None = None,
    error_message: str | None = _SENTINEL,
) -> dict[str, Any] | None:
    """Update a document's status and/or error message; None if unknown.

    Pass ``error_message=None`` to clear an error; omitting it keeps the
    current value.
    """
    existing = await get(doc_id)
    if existing is None:
        return None

    new_status = status if status is not None else existing["status"]
    new_error = error_message if error_message is not _SENTINEL else existing["error_message"]
    now = _utc_now_iso()

    conn = db.get_connection()
    await conn.execute(
        "UPDATE documents SET status = ?, error_message = ?, updated_at = ? WHERE id = ?",
        (new_status, new_error, now, doc_id),
    )
    await conn.commit()

    existing["status"] = new_status
    existing["error_message"] = new_error
    existing["updated_at"] = now
    return existing


async def delete(doc_id: str) -> bool:
    """Delete the document, returning whether a row was removed."""
    conn = db.get_connection()
    cursor = await conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await conn.commit()
    return cursor.rowcount > 0
