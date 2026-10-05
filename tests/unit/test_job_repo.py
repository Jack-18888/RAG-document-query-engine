import pytest

from app.storage import db, document_repo, job_repo


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "engine.db"
    await db.open_database(str(db_path))
    yield db.get_connection()
    await db.close_database()


async def _create_doc() -> str:
    doc = await document_repo.create("notes.md", "md", 1024)
    return doc["id"]


async def test_create_returns_job_with_initial_state(conn):
    doc_id = await _create_doc()

    job = await job_repo.create(doc_id)

    assert job["id"].startswith("job_")
    assert job["document_id"] == doc_id
    assert job["stage"] == "parsing"
    assert job["chunks_processed"] == 0
    assert job["chunks_total"] is None
    assert job["error_message"] is None
    assert job["created_at"] is not None
    assert job["updated_at"] is not None
    assert job["created_at"] == job["updated_at"]


async def test_create_persists_to_database(conn):
    doc_id = await _create_doc()
    job = await job_repo.create(doc_id)

    async with conn.execute(
        "SELECT id, document_id, stage, chunks_processed FROM jobs WHERE id = ?",
        (job["id"],),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row["document_id"] == doc_id
    assert row["stage"] == "parsing"
    assert row["chunks_processed"] == 0


async def test_get_existing(conn):
    doc_id = await _create_doc()
    created = await job_repo.create(doc_id)

    fetched = await job_repo.get(created["id"])

    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["document_id"] == doc_id


async def test_get_unknown_returns_none(conn):
    assert await job_repo.get("job_nonexistent") is None


async def test_update_stage(conn):
    doc_id = await _create_doc()
    job = await job_repo.create(doc_id)

    updated = await job_repo.update(job["id"], stage="chunking")

    assert updated is not None
    assert updated["stage"] == "chunking"
    assert updated["updated_at"] >= job["updated_at"]


async def test_update_chunk_counters(conn):
    doc_id = await _create_doc()
    job = await job_repo.create(doc_id)

    updated = await job_repo.update(job["id"], chunks_processed=2, chunks_total=5)

    assert updated is not None
    assert updated["chunks_processed"] == 2
    assert updated["chunks_total"] == 5


async def test_update_error_message(conn):
    doc_id = await _create_doc()
    job = await job_repo.create(doc_id)

    updated = await job_repo.update(job["id"], stage="failed", error_message="quota exceeded")

    assert updated is not None
    assert updated["stage"] == "failed"
    assert updated["error_message"] == "quota exceeded"


async def test_update_clear_error_message(conn):
    doc_id = await _create_doc()
    job = await job_repo.create(doc_id)
    await job_repo.update(job["id"], error_message="oops")

    updated = await job_repo.update(job["id"], error_message=None)

    assert updated is not None
    assert updated["error_message"] is None


async def test_update_refreshes_updated_at(conn, monkeypatch):
    doc_id = await _create_doc()
    monkeypatch.setattr(job_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:00Z")
    job = await job_repo.create(doc_id)
    monkeypatch.setattr(job_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:05Z")

    updated = await job_repo.update(job["id"], stage="indexing")

    assert updated["updated_at"] == "2025-01-01T00:00:05Z"
    assert updated["updated_at"] > job["updated_at"]


async def test_update_unknown_returns_none(conn):
    assert await job_repo.update("job_nonexistent", stage="chunking") is None


async def test_update_preserves_fields_not_passed(conn):
    doc_id = await _create_doc()
    job = await job_repo.create(doc_id)
    await job_repo.update(job["id"], stage="indexing", chunks_total=3)

    updated = await job_repo.get(job["id"])

    assert updated["stage"] == "indexing"
    assert updated["chunks_total"] == 3
    assert updated["chunks_processed"] == 0
    assert updated["error_message"] is None
