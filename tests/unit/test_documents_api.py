from pathlib import Path

import pytest


class _FakeExecutor:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, job_id, path):
        self.enqueued.append((job_id, path))

    def shutdown(self):
        pass


@pytest.fixture
def fake_executor(client):
    executor = _FakeExecutor()
    from app.api import documents as documents_api

    client.app.dependency_overrides[documents_api._executor] = lambda: executor
    return executor


def test_upload_returns_202_with_document_and_job(client, fake_executor):
    response = client.post(
        "/documents",
        files={"file": ("notes.md", b"# Hello\n\nWorld content.", "text/markdown")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["document"]["name"] == "notes.md"
    assert body["document"]["format"] == "md"
    assert body["document"]["status"] == "pending"
    assert body["job"]["document_id"] == body["document"]["id"]
    assert body["job"]["stage"] == "parsing"
    assert len(fake_executor.enqueued) == 1


def test_upload_saves_original_to_uploads(client, fake_executor, tmp_path):
    response = client.post(
        "/documents",
        files={"file": ("notes.md", b"# Hello", "text/markdown")},
    )
    doc_id = response.json()["document"]["id"]

    stored = Path(tmp_path / "uploads" / f"{doc_id}.md")
    assert stored.exists()
    assert stored.read_bytes() == b"# Hello"


def test_upload_unsupported_extension_returns_400(client):
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_upload_empty_file_returns_400(client):
    response = client.post(
        "/documents",
        files={"file": ("empty.md", b"", "text/markdown")},
    )

    assert response.status_code == 400


def test_upload_over_size_limit_returns_413(client, tmp_path, monkeypatch):
    from app.api import documents as documents_api

    monkeypatch.setattr(
        documents_api,
        "get_settings",
        lambda: type("S", (), {"upload_dir": str(tmp_path / "uploads"), "max_upload_size_mb": 0}),
    )

    response = client.post(
        "/documents",
        files={"file": ("big.md", b"x" * 10, "text/markdown")},
    )

    assert response.status_code == 413


def test_list_documents_newest_first(client, fake_executor):
    client.post("/documents", files={"file": ("first.md", b"# One", "text/markdown")})
    client.post("/documents", files={"file": ("second.md", b"# Two", "text/markdown")})

    response = client.get("/documents")

    assert response.status_code == 200
    documents = response.json()["documents"]
    assert [d["name"] for d in documents] == ["second.md", "first.md"]


def test_get_document_detail_returns_chunk_count(client, fake_executor):
    created = client.post(
        "/documents", files={"file": ("notes.md", b"# Hello", "text/markdown")}
    ).json()["document"]

    response = client.get(f"/documents/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert "chunk_count" in body


def test_get_document_unknown_returns_404(client):
    response = client.get("/documents/doc_nonexistent")

    assert response.status_code == 404


def test_job_status_endpoint(client, fake_executor):
    created = client.post(
        "/documents", files={"file": ("notes.md", b"# Hello", "text/markdown")}
    ).json()
    job_id = created["job"]["id"]

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job_id
    assert body["stage"] == "parsing"


def test_job_unknown_returns_404(client):
    response = client.get("/jobs/job_nonexistent")

    assert response.status_code == 404


def test_delete_document_returns_204(client, fake_executor, fake_pinecone, tmp_path, monkeypatch):
    created = client.post(
        "/documents", files={"file": ("notes.md", b"# Hello", "text/markdown")}
    ).json()["document"]

    response = client.delete(f"/documents/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/documents/{created['id']}").status_code == 404


def test_delete_unknown_returns_404(client, fake_pinecone):
    response = client.delete("/documents/doc_nonexistent")

    assert response.status_code == 404


def test_reindex_returns_202_with_fresh_job(client, fake_executor, fake_pinecone):
    created = client.post(
        "/documents", files={"file": ("notes.md", b"# Hello", "text/markdown")}
    ).json()["document"]

    response = client.post(f"/documents/{created['id']}/reindex")

    assert response.status_code == 202
    assert response.json()["job"]["document_id"] == created["id"]
    assert len(fake_executor.enqueued) == 2


def test_reindex_unknown_returns_404(client, fake_pinecone):
    response = client.post("/documents/doc_nonexistent/reindex")

    assert response.status_code == 404
