import pytest

from app.storage import chunk_repo, db, document_repo


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "engine.db"
    await db.open_database(str(db_path))
    yield db.get_connection()
    await db.close_database()


def _chunk(cid: str, doc_id: str, index: int, text: str, tokens: int = 3) -> chunk_repo.Chunk:
    return chunk_repo.Chunk(id=cid, doc_id=doc_id, chunk_index=index, text=text, tokens=tokens)


async def test_insert_many_persists_rows(conn):
    doc = await document_repo.create("notes.md", "md", 1024)

    await chunk_repo.insert_many(
        [
            _chunk("chunk_a", doc["id"], 0, "alpha beta gamma"),
            _chunk("chunk_b", doc["id"], 1, "delta epsilon zeta"),
        ]
    )

    async with conn.execute(
        "SELECT id, doc_id, chunk_index, text, tokens FROM chunks ORDER BY chunk_index"
    ) as cursor:
        rows = await cursor.fetchall()

    assert len(rows) == 2
    assert rows[0]["id"] == "chunk_a"
    assert rows[0]["doc_id"] == doc["id"]
    assert rows[0]["text"] == "alpha beta gamma"
    assert rows[0]["tokens"] == 3


async def test_insert_many_syncs_fts_rows(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    await chunk_repo.insert_many([_chunk("chunk_a", doc["id"], 0, "alpha beta gamma")])

    async with conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alpha'"
    ) as cursor:
        hits = await cursor.fetchall()

    assert len(hits) == 1


async def test_insert_many_commits_as_one_transaction(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    await chunk_repo.insert_many(
        [_chunk("chunk_a", doc["id"], 0, "alpha"), _chunk("chunk_b", doc["id"], 1, "beta")]
    )

    async with conn.execute("SELECT COUNT(*) FROM chunks") as cursor:
        row = await cursor.fetchone()
    assert row[0] == 2


async def test_count_by_document(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    other = await document_repo.create("other.md", "md", 512)
    await chunk_repo.insert_many(
        [_chunk("c1", doc["id"], 0, "alpha"), _chunk("c2", doc["id"], 1, "beta")]
    )
    await chunk_repo.insert_many([_chunk("c3", other["id"], 0, "gamma")])

    assert await chunk_repo.count_by_document(doc["id"]) == 2
    assert await chunk_repo.count_by_document(other["id"]) == 1
    assert await chunk_repo.count_by_document("doc_nonexistent") == 0


async def test_list_by_document_ordered(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    await chunk_repo.insert_many(
        [
            _chunk("c2", doc["id"], 1, "beta"),
            _chunk("c0", doc["id"], 0, "alpha"),
            _chunk("c3", doc["id"], 2, "gamma"),
        ]
    )

    chunks = await chunk_repo.list_by_document(doc["id"])

    assert [c.id for c in chunks] == ["c0", "c2", "c3"]
    assert chunks[0].text == "alpha"


async def test_list_by_document_scoped_to_document(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    other = await document_repo.create("other.md", "md", 512)
    await chunk_repo.insert_many([_chunk("c1", doc["id"], 0, "alpha")])
    await chunk_repo.insert_many([_chunk("c2", other["id"], 0, "beta")])

    chunks = await chunk_repo.list_by_document(doc["id"])

    assert [c.id for c in chunks] == ["c1"]


async def test_list_by_document_empty(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    assert await chunk_repo.list_by_document(doc["id"]) == []


async def test_delete_by_document_removes_rows(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    other = await document_repo.create("other.md", "md", 512)
    await chunk_repo.insert_many(
        [_chunk("c1", doc["id"], 0, "alpha"), _chunk("c2", doc["id"], 1, "beta")]
    )
    await chunk_repo.insert_many([_chunk("c3", other["id"], 0, "gamma")])

    await chunk_repo.delete_by_document(doc["id"])

    assert await chunk_repo.count_by_document(doc["id"]) == 0
    assert await chunk_repo.count_by_document(other["id"]) == 1


async def test_delete_by_document_removes_fts_rows(conn):
    doc = await document_repo.create("notes.md", "md", 1024)
    await chunk_repo.insert_many([_chunk("c1", doc["id"], 0, "alpha beta gamma")])

    await chunk_repo.delete_by_document(doc["id"])

    async with conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alpha'"
    ) as cursor:
        hits = await cursor.fetchall()
    assert hits == []


async def test_delete_by_document_unknown_doc_is_noop(conn):
    await chunk_repo.delete_by_document("doc_nonexistent")
    assert await chunk_repo.count_by_document("doc_nonexistent") == 0
