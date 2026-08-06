import pytest

from app.retrieval.retrieval_service import (
    FUSION_TOP_K,
    NO_SOURCES_MESSAGE,
    RetrievalService,
)
from app.storage import chunk_repo, db, document_repo


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "engine.db"
    await db.open_database(str(db_path))
    yield db.get_connection()
    await db.close_database()


def _dense(values):
    return type("Embedding", (), {"values": values})


def _match(chunk_id, score):
    return type("Match", (), {"id": chunk_id, "score": score, "metadata": {"doc_id": "doc_1"}})


class _FakeInference:
    def __init__(self, vectors):
        self.vectors = vectors

    async def embed(self, model, inputs, parameters):
        return type("Embeddings", (), {"data": [_dense(self.vectors) for _ in inputs]})

    async def rerank(
        self, model, query, documents, rank_fields, top_n, return_documents, parameters
    ):
        items = [
            type("Item", (), {"index": i, "score": 1.0 - i * 0.1})
            for i in range(min(top_n, len(documents)))
        ]
        return type("RerankResponse", (), {"data": items})


class _FakeIndex:
    def __init__(self, matches):
        self.matches = matches

    async def query(self, *, vector, top_k, namespace, include_metadata):
        return type("QueryResponse", (), {"matches": self.matches[:top_k]})


class _FakeClient:
    def __init__(self, vectors, matches):
        self.inference_handle = _FakeInference(vectors)
        self.index_handle = _FakeIndex(matches)

    async def inference(self):
        return self.inference_handle

    async def index(self):
        return self.index_handle


async def _no_sleep(_seconds: float) -> None:
    return None


async def _seed(conn, tmp_path):
    doc = await document_repo.create("notes.md", "md", 1024)
    await chunk_repo.insert_many(
        [
            chunk_repo.Chunk("chunk_a", doc["id"], 0, "the quick brown fox", 5),
            chunk_repo.Chunk("chunk_b", doc["id"], 1, "nothing to see here", 5),
            chunk_repo.Chunk("chunk_c", doc["id"], 2, "fox fox fox jumps", 5),
        ]
    )
    return doc


def _make_service(fake_client):
    return RetrievalService(fake_client, sleep=_no_sleep)


async def test_retrieve_returns_top_3_reranked_chunks(conn, tmp_path):
    doc = await _seed(conn, tmp_path)
    client = _FakeClient(
        vectors=[0.1, 0.2],
        matches=[_match("chunk_a", 0.9), _match("chunk_c", 0.8), _match("chunk_b", 0.7)],
    )

    results = await _make_service(client).retrieve("fox")

    assert len(results) == 3
    assert [r.chunk_id for r in results] == ["chunk_a", "chunk_c", "chunk_b"]
    assert results[0].doc_id == doc["id"]
    assert results[0].doc_name == "notes.md"
    assert results[0].score == 1.0


async def test_empty_vector_and_bm25_returns_empty(conn, tmp_path):
    await _seed(conn, tmp_path)
    client = _FakeClient(vectors=[0.1], matches=[])

    results = await _make_service(client).retrieve("nothing that matches")

    assert results == []


async def test_no_rerank_when_no_candidates(conn, tmp_path):
    await _seed(conn, tmp_path)
    client = _FakeClient(vectors=[0.1], matches=[])

    service = _make_service(client)
    results = await service.retrieve("xyz")

    assert results == []


async def test_retrieved_chunk_text_present(conn, tmp_path):
    await _seed(conn, tmp_path)
    client = _FakeClient(vectors=[0.1], matches=[_match("chunk_a", 0.9)])

    results = await _make_service(client).retrieve("fox")

    assert results[0].text == "the quick brown fox"


def test_no_sources_message_constant():
    assert NO_SOURCES_MESSAGE == "No relevant sources found in the library."
    assert FUSION_TOP_K == 20
