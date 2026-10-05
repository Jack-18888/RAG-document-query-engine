import pytest

from app.retrieval.vector_repo import UPSERT_BATCH_SIZE, VectorRepository, VectorRepositoryError


def _match(chunk_id, score, metadata=None):
    return type("Match", (), {"id": chunk_id, "score": score, "metadata": metadata or {}})


class _FakeIndex:
    def __init__(self):
        self.upserts: list[list] = []
        self.query_calls = []
        self.delete_filters = []
        self.matches = []
        self.upsert_failures = 0
        self.query_failures = 0
        self.delete_failures = 0
        self._upsert_failed = 0
        self._query_failed = 0
        self._delete_failed = 0

    async def upsert(self, *, vectors, namespace):
        self.upserts.append(list(vectors))
        if self._upsert_failed < self.upsert_failures:
            self._upsert_failed += 1
            raise TimeoutError("transient")
        return None

    async def query(self, *, vector, top_k, namespace, include_metadata):
        self.query_calls.append(
            {"vector": vector, "top_k": top_k, "include_metadata": include_metadata}
        )
        if self._query_failed < self.query_failures:
            self._query_failed += 1
            raise TimeoutError("transient")
        return type("QueryResponse", (), {"matches": self.matches})

    async def delete(self, *, filter, namespace):
        self.delete_filters.append(filter)
        if self._delete_failed < self.delete_failures:
            self._delete_failed += 1
            raise TimeoutError("transient")
        return None


class _FakeClient:
    def __init__(self, index=None):
        self.index_handle = index or _FakeIndex()

    async def index(self):
        return self.index_handle


async def _no_sleep(_seconds: float) -> None:
    return None


def _repo(client=None):
    index = client.index_handle if client else _FakeIndex()
    return VectorRepository(client or _FakeClient(index), sleep=_no_sleep), index


async def test_upsert_writes_vectors_with_ids_and_metadata():
    repo, index = _repo()

    await repo.upsert(["chunk_1", "chunk_2"], [[0.1, 0.2], [0.3, 0.4]], "doc_1")

    assert len(index.upserts) == 1
    batch = index.upserts[0]
    assert len(batch) == 2
    assert batch[0] == ("chunk_1", [0.1, 0.2], {"doc_id": "doc_1"})
    assert batch[1] == ("chunk_2", [0.3, 0.4], {"doc_id": "doc_1"})


async def test_upsert_batches_at_100():
    repo, index = _repo()

    await repo.upsert([f"c{i}" for i in range(250)], [[0.0]] * 250, "doc_1")

    assert [len(b) for b in index.upserts] == [100, 100, 50]


async def test_upsert_mismatched_lengths_raises():
    repo, _ = _repo()

    with pytest.raises(VectorRepositoryError, match="same length"):
        await repo.upsert(["chunk_1"], [[0.1], [0.2]], "doc_1")


async def test_query_returns_matches_with_scores_and_metadata():
    repo, index = _repo()
    index.matches = [
        _match("chunk_a", 0.89, {"doc_id": "doc_1"}),
        _match("chunk_b", 0.72, {"doc_id": "doc_2"}),
    ]

    results = await repo.query([0.1, 0.2], top_k=5)

    assert len(results) == 2
    assert results[0] == {
        "chunk_id": "chunk_a",
        "score": 0.89,
        "metadata": {"doc_id": "doc_1"},
    }
    assert results[1]["chunk_id"] == "chunk_b"
    assert index.query_calls[0]["top_k"] == 5
    assert index.query_calls[0]["include_metadata"] is True


async def test_query_empty_matches():
    repo, _ = _repo()

    results = await repo.query([0.1, 0.2])

    assert results == []


async def test_delete_by_document_uses_metadata_filter():
    repo, index = _repo()

    await repo.delete_by_document("doc_1")

    assert index.delete_filters == [{"doc_id": "doc_1"}]


async def test_transient_failures_retried(monkeypatch):
    client = _FakeClient()
    index = client.index_handle
    index.upsert_failures = 1
    repo = VectorRepository(client, sleep=_no_sleep)

    await repo.upsert(["chunk_1"], [[0.1]], "doc_1")

    assert len(index.upserts) == 2


async def test_persistent_upsert_failure_raises(monkeypatch):
    client = _FakeClient()
    index = client.index_handle
    index.upsert_failures = 10
    repo = VectorRepository(client, sleep=_no_sleep)

    with pytest.raises(VectorRepositoryError, match="upsert failed"):
        await repo.upsert(["chunk_1"], [[0.1]], "doc_1")


async def test_persistent_query_failure_raises(monkeypatch):
    client = _FakeClient()
    index = client.index_handle
    index.query_failures = 10
    repo = VectorRepository(client, sleep=_no_sleep)

    with pytest.raises(VectorRepositoryError, match="query failed"):
        await repo.query([0.1])


async def test_persistent_delete_failure_raises(monkeypatch):
    client = _FakeClient()
    index = client.index_handle
    index.delete_failures = 10
    repo = VectorRepository(client, sleep=_no_sleep)

    with pytest.raises(VectorRepositoryError, match="delete failed"):
        await repo.delete_by_document("doc_1")


def test_upsert_batch_size_constant():
    assert UPSERT_BATCH_SIZE == 100
