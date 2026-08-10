import pytest

from app.storage import db, document_repo


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "engine.db"
    await db.open_database(str(db_path))
    yield db.get_connection()
    await db.close_database()


async def test_create_returns_pending_with_timestamps(conn):
    doc = await document_repo.create("notes.md", "md", 1024)

    assert doc["id"].startswith("doc_")
    assert doc["name"] == "notes.md"
    assert doc["format"] == "md"
    assert doc["size_bytes"] == 1024
    assert doc["status"] == "pending"
    assert doc["error_message"] is None
    assert doc["created_at"] is not None
    assert doc["updated_at"] is not None
    assert doc["created_at"] == doc["updated_at"]


async def test_create_persists_to_database(conn):
    doc = await document_repo.create("report.pdf", "pdf", 5000)

    async with conn.execute(
        "SELECT id, name, format, size_bytes, status FROM documents WHERE id = ?",
        (doc["id"],),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row["name"] == "report.pdf"
    assert row["status"] == "pending"


async def test_list_all_returns_newest_first(conn, monkeypatch):
    monkeypatch.setattr(document_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:00Z")
    doc_a = await document_repo.create("first.md", "md", 100)
    monkeypatch.setattr(document_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:01Z")
    doc_b = await document_repo.create("second.md", "md", 200)

    docs = await document_repo.list_all()
    assert len(docs) == 2
    assert docs[0]["id"] == doc_b["id"]
    assert docs[1]["id"] == doc_a["id"]


async def test_list_all_empty(conn):
    docs = await document_repo.list_all()
    assert docs == []


async def test_get_existing(conn):
    created = await document_repo.create("readme.md", "md", 512)

    fetched = await document_repo.get(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "readme.md"


async def test_get_unknown_returns_none(conn):
    result = await document_repo.get("doc_nonexistent")
    assert result is None


async def test_update_status(conn):
    doc = await document_repo.create("file.html", "html", 300)

    updated = await document_repo.update(doc["id"], status="indexed")
    assert updated is not None
    assert updated["status"] == "indexed"
    assert updated["updated_at"] >= doc["updated_at"]


async def test_update_error_message(conn):
    doc = await document_repo.create("file.pdf", "pdf", 400)

    updated = await document_repo.update(doc["id"], status="failed", error_message="parse error")
    assert updated is not None
    assert updated["status"] == "failed"
    assert updated["error_message"] == "parse error"


async def test_update_clear_error_message(conn):
    doc = await document_repo.create("file.docx", "docx", 500)
    await document_repo.update(doc["id"], status="failed", error_message="oops")

    updated = await document_repo.update(doc["id"], status="pending", error_message=None)
    assert updated is not None
    assert updated["error_message"] is None
    assert updated["status"] == "pending"


async def test_update_refreshes_updated_at(conn, monkeypatch):
    monkeypatch.setattr(document_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:00Z")
    doc = await document_repo.create("ts.md", "md", 100)
    monkeypatch.setattr(document_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:05Z")

    updated = await document_repo.update(doc["id"], status="indexed")
    assert updated["updated_at"] == "2025-01-01T00:00:05Z"
    assert updated["updated_at"] > doc["updated_at"]


async def test_update_unknown_returns_none(conn):
    result = await document_repo.update("doc_nonexistent", status="indexed")
    assert result is None


async def test_delete_existing(conn):
    doc = await document_repo.create("delete_me.md", "md", 100)

    assert await document_repo.delete(doc["id"]) is True
    assert await document_repo.get(doc["id"]) is None


async def test_delete_unknown_returns_false(conn):
    assert await document_repo.delete("doc_nonexistent") is False


async def test_update_preserves_fields_not_passed(conn):
    doc = await document_repo.create("keep.md", "md", 256)
    await document_repo.update(doc["id"], status="indexed")

    fetched = await document_repo.get(doc["id"])
    assert fetched["name"] == "keep.md"
    assert fetched["format"] == "md"
    assert fetched["size_bytes"] == 256
    assert fetched["status"] == "indexed"
    assert fetched["error_message"] is None
