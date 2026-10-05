from app.main import create_app


def _all_paths(app):
    return set(app.openapi()["paths"])


def test_all_contract_endpoints_registered():
    app = create_app()
    paths = _all_paths(app)

    assert "/health" in paths
    assert "/documents" in paths
    assert "/documents/{doc_id}" in paths
    assert "/documents/{doc_id}/reindex" in paths
    assert "/jobs/{job_id}" in paths
    assert "/queries" in paths
    assert "/queries/{query_id}" in paths


def test_health_no_external_calls(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_error_shape_is_detail(client, fake_executor, fake_pinecone):
    response = client.get("/documents/doc_missing")

    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


def test_document_detail_chunk_count_zero_for_pending(client, fake_executor):
    doc = client.post(
        "/documents", files={"file": ("notes.md", b"# Hello", "text/markdown")}
    ).json()["document"]

    response = client.get(f"/documents/{doc['id']}")

    assert response.status_code == 200
    assert response.json()["chunk_count"] == 0


def test_reindex_missing_stored_file_returns_404(client, fake_executor, fake_pinecone, tmp_path):
    doc = client.post(
        "/documents", files={"file": ("ghost.md", b"# Ghost", "text/markdown")}
    ).json()["document"]
    stored = tmp_path / "uploads" / f"{doc['id']}.md"
    assert stored.exists()
    stored.unlink()

    response = client.post(f"/documents/{doc['id']}/reindex")

    assert response.status_code == 404
