import pytest

from app.storage import bm25_repo, chunk_repo, db, document_repo


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "engine.db"
    await db.open_database(str(db_path))
    yield db.get_connection()
    await db.close_database()


def _chunk(cid: str, doc_id: str, index: int, text: str) -> chunk_repo.Chunk:
    return chunk_repo.Chunk(id=cid, doc_id=doc_id, chunk_index=index, text=text, tokens=3)


async def _seed_doc() -> str:
    doc = await document_repo.create("notes.md", "md", 1024)
    await chunk_repo.insert_many(
        [
            _chunk("chunk_a", doc["id"], 0, "the quick brown fox"),
            _chunk("chunk_b", doc["id"], 1, "nothing to see here"),
            _chunk("chunk_c", doc["id"], 2, "fox fox fox fox jumps"),
            _chunk("chunk_d", doc["id"], 3, "a lazy dog sleeps"),
        ]
    )
    return doc["id"]


async def test_search_returns_chunk_ids_by_rank(conn):
    await _seed_doc()

    hits = await bm25_repo.search("fox")

    assert "chunk_c" in hits
    assert "chunk_a" in hits
    assert hits[0] == "chunk_c"
    assert len(hits) == 2


async def test_search_orders_best_match_first(conn):
    await _seed_doc()

    hits = await bm25_repo.search("fox")

    assert hits == ["chunk_c", "chunk_a"]


async def test_search_respects_top_k(conn):
    await _seed_doc()

    hits = await bm25_repo.search("fox", k=1)

    assert hits == ["chunk_c"]


async def test_search_no_matches_returns_empty(conn):
    await _seed_doc()

    assert await bm25_repo.search("zebra") == []


async def test_search_special_characters_do_not_error(conn):
    await _seed_doc()

    for query in ['"', "*", "(", "foo:bar", "fox!", "a b?", "NOT", "NEAR(a,b)", ""]:
        hits = await bm25_repo.search(query)
        assert isinstance(hits, list)


async def test_search_punctuation_still_matches_terms(conn):
    await _seed_doc()

    hits = await bm25_repo.search("quick, brown!")

    assert "chunk_a" in hits


async def test_search_multi_word_requires_all_terms(conn):
    await _seed_doc()

    hits = await bm25_repo.search("fox dog")

    assert hits == []


async def test_search_whitespace_only_returns_empty(conn):
    await _seed_doc()

    assert await bm25_repo.search("   ") == []


async def test_search_scoped_to_seeded_chunks_only(conn):
    other = await document_repo.create("other.md", "md", 512)
    await chunk_repo.insert_many([_chunk("chunk_other", other["id"], 0, "fox in other doc")])
    await _seed_doc()

    hits = await bm25_repo.search("fox")

    assert "chunk_other" in hits
