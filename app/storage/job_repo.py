"""SQLite repository for ingestion jobs."""

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
    """Return a new unique job id."""
    return f"job_{uuid.uuid4().hex[:12]}"


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an aiosqlite row into a plain dict."""
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "stage": row["stage"],
        "chunks_processed": row["chunks_processed"],
        "chunks_total": row["chunks_total"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def create(document_id: str) -> dict[str, Any]:
    """Insert a new job for ``document_id`` starting in the ``parsing`` stage."""
    conn = db.get_connection()
    job_id = _generate_id()
    now = _utc_now_iso()
    await conn.execute(
        "INSERT INTO jobs "
        "(id, document_id, stage, chunks_processed, chunks_total, error_message, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, document_id, "parsing", 0, None, None, now, now),
    )
    await conn.commit()
    return {
        "id": job_id,
        "document_id": document_id,
        "stage": "parsing",
        "chunks_processed": 0,
        "chunks_total": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }


async def get(job_id: str) -> dict[str, Any] | None:
    """Return the job record, or None if it does not exist."""
    conn = db.get_connection()
    async with conn.execute(
        "SELECT id, document_id, stage, chunks_processed, chunks_total, error_message, "
        "created_at, updated_at FROM jobs WHERE id = ?",
        (job_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


async def update(
    job_id: str,
    *,
    stage: str | None = None,
    chunks_processed: int | None = None,
    chunks_total: int | None = None,
    error_message: str | None = _SENTINEL,
) -> dict[str, Any] | None:
    """Update any of a job's progress fields; None if the job is unknown.

    Only fields that are not None (or, for ``error_message``, not the sentinel)
    are applied; ``error_message=None`` clears an error.
    """
    existing = await get(job_id)
    if existing is None:
        return None

    new_stage = stage if stage is not None else existing["stage"]
    new_processed = (
        chunks_processed if chunks_processed is not None else existing["chunks_processed"]
    )
    new_total = chunks_total if chunks_total is not None else existing["chunks_total"]
    new_error = error_message if error_message is not _SENTINEL else existing["error_message"]
    now = _utc_now_iso()

    conn = db.get_connection()
    await conn.execute(
        "UPDATE jobs SET stage = ?, chunks_processed = ?, chunks_total = ?, "
        "error_message = ?, updated_at = ? WHERE id = ?",
        (new_stage, new_processed, new_total, new_error, now, job_id),
    )
    await conn.commit()

    existing["stage"] = new_stage
    existing["chunks_processed"] = new_processed
    existing["chunks_total"] = new_total
    existing["error_message"] = new_error
    existing["updated_at"] = now
    return existing
