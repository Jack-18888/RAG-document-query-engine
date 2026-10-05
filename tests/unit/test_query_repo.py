import pytest

from app.storage import db, query_repo


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "engine.db"
    await db.open_database(str(db_path))
    yield db.get_connection()
    await db.close_database()


async def _insert_document_with_chunks(conn, doc_id="doc_1", name="notes.md"):
    await conn.execute(
        "INSERT INTO documents (id, name, format, size_bytes) VALUES (?, ?, ?, ?)",
        (doc_id, name, "md", 12),
    )
    await conn.executemany(
        "INSERT INTO chunks (id, doc_id, chunk_index, text, tokens) VALUES (?, ?, ?, ?, ?)",
        [
            (f"chunk_{doc_id}_0", doc_id, 0, "Invoices kept 7 years.", 4),
            (f"chunk_{doc_id}_1", doc_id, 1, "Tax records kept 10 years.", 5),
        ],
    )
    await conn.commit()


async def test_create_returns_record_with_metadata(conn):
    record = await query_repo.create("retention period?", "7 years.", [])

    assert record["id"].startswith("query_")
    assert record["question"] == "retention period?"
    assert record["answer"] == "7 years."
    assert record["created_at"] is not None


async def test_create_persists_query_row(conn):
    record = await query_repo.create("question?", "answer", [])

    async with conn.execute(
        "SELECT id, question, answer FROM queries WHERE id = ?",
        (record["id"],),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row["question"] == "question?"
    assert row["answer"] == "answer"


async def test_create_persists_fetched_chunks(conn):
    await _insert_document_with_chunks(conn)
    record = await query_repo.create(
        "retention period?",
        "7 years.",
        [("chunk_doc_1_0", 0.89), ("chunk_doc_1_1", 0.51)],
    )

    async with conn.execute(
        "SELECT chunk_id, score FROM query_chunks WHERE query_id = ? ORDER BY rowid",
        (record["id"],),
    ) as cursor:
        rows = await cursor.fetchall()

    assert [row["chunk_id"] for row in rows] == ["chunk_doc_1_0", "chunk_doc_1_1"]
    assert [row["score"] for row in rows] == [0.89, 0.51]


async def test_list_all_returns_newest_first(conn, monkeypatch):
    monkeypatch.setattr(query_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:00Z")
    query_a = await query_repo.create("first?", "a", [])
    monkeypatch.setattr(query_repo, "_utc_now_iso", lambda: "2025-01-01T00:00:01Z")
    query_b = await query_repo.create("second?", "b", [])

    queries = await query_repo.list_all()
    assert len(queries) == 2
    assert queries[0]["id"] == query_b["id"]
    assert queries[1]["id"] == query_a["id"]


async def test_list_all_empty(conn):
    assert await query_repo.list_all() == []


async def test_get_existing(conn):
    created = await query_repo.create("question?", "answer", [])

    fetched = await query_repo.get(created["id"])
    assert fetched is not None
    assert fetched["question"] == "question?"
    assert fetched["answer"] == "answer"


async def test_get_unknown_returns_none(conn):
    assert await query_repo.get("query_nonexistent") is None


async def test_get_sources_joins_chunk_and_document(conn):
    await _insert_document_with_chunks(conn, doc_id="doc_7", name="tax.md")
    record = await query_repo.create(
        "retention period?",
        "7 years.",
        [("chunk_doc_7_0", 0.89), ("chunk_doc_7_1", 0.51)],
    )

    sources = await query_repo.get_sources(record["id"])

    assert len(sources) == 2
    assert sources[0] == {
        "chunk_id": "chunk_doc_7_0",
        "doc_id": "doc_7",
        "doc_name": "tax.md",
        "excerpt": "Invoices kept 7 years.",
        "score": 0.89,
    }
    assert sources[1]["chunk_id"] == "chunk_doc_7_1"
    assert sources[1]["score"] == 0.51


async def test_get_sources_orders_by_insertion(conn):
    await _insert_document_with_chunks(conn)
    record = await query_repo.create(
        "q",
        "a",
        [("chunk_doc_1_1", 0.4), ("chunk_doc_1_0", 0.9)],
    )

    sources = await query_repo.get_sources(record["id"])

    assert [s["chunk_id"] for s in sources] == ["chunk_doc_1_1", "chunk_doc_1_0"]


async def test_get_sources_drops_deleted_chunks(conn):
    await _insert_document_with_chunks(conn)
    record = await query_repo.create("q", "a", [("chunk_doc_1_0", 0.89)])

    await conn.execute("DELETE FROM chunks WHERE id = 'chunk_doc_1_0'")
    await conn.commit()

    assert await query_repo.get_sources(record["id"]) == []


async def test_delete_removes_query_and_relations(conn):
    await _insert_document_with_chunks(conn)
    record = await query_repo.create("q", "a", [("chunk_doc_1_0", 0.89)])

    assert await query_repo.delete(record["id"]) is True
    assert await query_repo.get(record["id"]) is None

    async with conn.execute(
        "SELECT COUNT(*) FROM query_chunks WHERE query_id = ?",
        (record["id"],),
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == 0


async def test_delete_unknown_returns_false(conn):
    assert await query_repo.delete("query_nonexistent") is False
