import asyncio
import time

import pytest

from app.jobs.worker import JobExecutor, ingest_job
from app.storage import db, document_repo, job_repo


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "engine.db"
    await db.open_database(str(db_path))
    yield db.get_connection()
    await db.close_database()


class _FakeInference:
    async def embed(self, model, inputs, parameters):
        return _FakeEmbeddings([{"values": [0.1] * 1024} for _ in inputs])


class _FakeEmbeddings:
    def __init__(self, data):
        self.data = [type("Embedding", (), {"values": item["values"]}) for item in data]


class _FakePineconeClient:
    def __init__(self):
        self.inference_handle = _FakeInference()
        self.index_handle = _FakeIndex()

    async def inference(self):
        return self.inference_handle

    async def index(self):
        return self.index_handle


class _FakeIndex:
    def __init__(self):
        self.upserts = []

    async def upsert(self, *, vectors, namespace):
        self.upserts.append(list(vectors))

    async def query(self, **kwargs):
        return type("QueryResponse", (), {"matches": []})

    async def delete(self, **kwargs):
        return None


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakePineconeClient()
    monkeypatch.setattr("app.jobs.worker.get_pinecone_client", lambda: client)
    return client


async def _enqueue_md(tmp_path, conn, content="Hello world."):
    doc = await document_repo.create("notes.md", "md", 100)
    job = await job_repo.create(doc["id"])
    path = tmp_path / f"{doc['id']}.md"
    path.write_text(content, encoding="utf-8")
    return doc, job, path


async def test_full_pipeline_marks_document_indexed(conn, tmp_path, fake_client):
    doc, job, path = await _enqueue_md(tmp_path, conn)

    await ingest_job(job["id"], path)

    fetched_doc = await document_repo.get(doc["id"])
    fetched_job = await job_repo.get(job["id"])
    assert fetched_doc["status"] == "indexed"
    assert fetched_job["stage"] == "succeeded"


async def test_chunks_stored_after_success(conn, tmp_path, fake_client):
    doc, job, path = await _enqueue_md(tmp_path, conn, "# Title\n\nbody text.")

    await ingest_job(job["id"], path)

    from app.storage import chunk_repo

    chunks = await chunk_repo.list_by_document(doc["id"])
    assert len(chunks) > 0
    assert chunks[0].doc_id == doc["id"]
    assert "Title" in chunks[0].text


async def test_vectors_upserted_with_doc_metadata(conn, tmp_path, fake_client):
    doc, job, path = await _enqueue_md(tmp_path, conn)

    await ingest_job(job["id"], path)

    index = fake_client.index_handle
    assert len(index.upserts) > 0
    first_batch = index.upserts[0]
    assert all(record[2] == {"doc_id": doc["id"]} for record in first_batch)


async def test_progress_stages_persisted(conn, tmp_path, fake_client, monkeypatch):
    doc, job, path = await _enqueue_md(tmp_path, conn)

    recorded = []

    original_update = job_repo.update

    async def recording_update(job_id, **kwargs):
        recorded.append(kwargs)
        return await original_update(job_id, **kwargs)

    monkeypatch.setattr("app.jobs.worker.job_repo.update", recording_update)

    await ingest_job(job["id"], path)

    stages = [call.get("stage") for call in recorded if "stage" in call]
    assert "parsing" in stages
    assert "chunking" in stages
    assert "embedding" in stages
    assert "indexing" in stages
    assert stages[-1] == "succeeded"


async def test_parse_failure_fails_job_and_document(conn, tmp_path, fake_client):
    doc = await document_repo.create("corrupt.docx", "docx", 100)
    job = await job_repo.create(doc["id"])
    path = tmp_path / f"{doc['id']}.docx"
    path.write_bytes(b"this is not a docx file")

    await ingest_job(job["id"], path)

    fetched_doc = await document_repo.get(doc["id"])
    fetched_job = await job_repo.get(job["id"])
    assert fetched_doc["status"] == "failed"
    assert fetched_doc["error_message"] is not None
    assert fetched_job["stage"] == "failed"
    assert fetched_job["error_message"] is not None


async def test_embed_failure_fails_job(conn, tmp_path, fake_client, monkeypatch):
    doc, job, path = await _enqueue_md(tmp_path, conn)

    async def boom(self, *args, **kwargs):
        raise RuntimeError("embed service down")

    monkeypatch.setattr("app.embeddings.embedding_service.EmbeddingService.embed", boom)

    await ingest_job(job["id"], path)

    fetched_doc = await document_repo.get(doc["id"])
    fetched_job = await job_repo.get(job["id"])
    assert fetched_doc["status"] == "failed"
    assert fetched_job["stage"] == "failed"


async def test_upsert_failure_leaves_no_local_chunks(conn, tmp_path, fake_client, monkeypatch):
    from app.storage import chunk_repo

    doc, job, path = await _enqueue_md(tmp_path, conn)

    async def boom(self, *args, **kwargs):
        raise RuntimeError("vector upsert down")

    monkeypatch.setattr("app.retrieval.vector_repo.VectorRepository.upsert", boom)

    await ingest_job(job["id"], path)

    fetched_doc = await document_repo.get(doc["id"])
    assert fetched_doc["status"] == "failed"
    assert await chunk_repo.count_by_document(doc["id"]) == 0


async def test_unknown_job_is_noop(conn, tmp_path, fake_client):
    await ingest_job("job_nonexistent", tmp_path / "x.md")
    assert True


async def test_executor_runs_job_in_thread_pool(conn, tmp_path, fake_client):
    doc, job, path = await _enqueue_md(tmp_path, conn)
    executor = JobExecutor(max_workers=2)

    executor.enqueue(job["id"], path)
    await _wait_until(lambda: _job_succeeded(job["id"]), timeout=10)
    executor.shutdown()

    fetched_doc = await document_repo.get(doc["id"])
    assert fetched_doc["status"] == "indexed"


async def _job_succeeded(job_id):
    from app.storage import job_repo

    job = await job_repo.get(job_id)
    return job is not None and job["stage"] == "succeeded"


async def _wait_until(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("timed out waiting for condition")
