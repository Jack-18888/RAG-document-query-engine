import sqlite3

import pytest

from app.retrieval.retrieval_service import NO_SOURCES_MESSAGE, RetrievedChunk


def _chunk(chunk_id, doc_id="doc_1", text="excerpt", score=0.9):
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_name="notes.md",
        text=text,
        score=score,
    )


class _FakeClient:
    def __init__(self):
        pass

    async def inference(self):
        return self

    async def index(self):
        return self


@pytest.fixture
def fake_query_services(client, monkeypatch):
    import app.api.queries as queries_api

    monkeypatch.setattr(
        "app.embeddings.pinecone_client.get_pinecone_client",
        lambda: _FakeClient(),
    )

    def install(retrieval=None, chat=None):
        if retrieval is not None:
            monkeypatch.setattr(queries_api.RetrievalService, "retrieve", retrieval)
        if chat is not None:
            monkeypatch.setattr(queries_api.DeepSeekClient, "chat", chat)

    return install


def test_query_returns_answer_and_sources(client, fake_query_services):
    async def fake_retrieve(self, question):
        return [_chunk("chunk_1", text="Invoices kept 7 years.", score=0.89)]

    async def fake_chat(self, messages, sleep=None):
        return "The retention policy requires 7 years."

    fake_query_services(retrieval=fake_retrieve, chat=fake_chat)

    response = client.post("/queries", json={"question": "retention period?"})

    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("query_")
    assert body["question"] == "retention period?"
    assert body["created_at"] is not None
    assert body["answer"] == "The retention policy requires 7 years."
    assert len(body["sources"]) == 1
    assert body["sources"][0]["chunk_id"] == "chunk_1"
    assert body["sources"][0]["doc_id"] == "doc_1"
    assert body["sources"][0]["doc_name"] == "notes.md"
    assert body["sources"][0]["excerpt"] == "Invoices kept 7 years."
    assert body["sources"][0]["score"] == 0.89


def test_query_no_sources_returns_canned_message_without_llm(client, fake_query_services):
    async def fake_retrieve(self, question):
        return []

    def chat_called(*args, **kwargs):
        raise AssertionError("chat must not be called when no sources")

    fake_query_services(retrieval=fake_retrieve, chat=chat_called)

    response = client.post("/queries", json={"question": "nothing"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == NO_SOURCES_MESSAGE
    assert body["sources"] == []


def test_query_missing_question_returns_400(client, fake_query_services):
    response = client.post("/queries", json={})

    assert response.status_code == 400


def test_query_empty_question_returns_400(client, fake_query_services):
    response = client.post("/queries", json={"question": "   "})

    assert response.status_code == 400


def test_query_hosted_failure_returns_503(client, fake_query_services):
    async def fake_retrieve(self, question):
        raise RuntimeError("pinecone down")

    fake_query_services(retrieval=fake_retrieve)

    response = client.post("/queries", json={"question": "hello"})

    assert response.status_code == 503
    assert "detail" in response.json()


def _seed_library_chunk(db_path, chunk_id="chunk_1", doc_id="doc_1", text="Invoices kept 7 years."):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO documents (id, name, format, size_bytes) VALUES (?, ?, ?, ?)",
            (doc_id, "notes.md", "md", 12),
        )
        conn.execute(
            "INSERT INTO chunks (id, doc_id, chunk_index, text, tokens) VALUES (?, ?, ?, ?, ?)",
            (chunk_id, doc_id, 0, text, 4),
        )


def _ask(client, fake_query_services, question="retention period?"):
    async def fake_retrieve(self, question):
        return [_chunk("chunk_1", text="Invoices kept 7 years.", score=0.89)]

    async def fake_chat(self, messages, sleep=None):
        return "The retention policy requires 7 years."

    fake_query_services(retrieval=fake_retrieve, chat=fake_chat)
    return client.post("/queries", json={"question": question})


def test_query_persists_and_no_sources_is_stored(client, fake_query_services):
    async def fake_retrieve(self, question):
        return []

    def chat_called(*args, **kwargs):
        raise AssertionError("chat must not be called when no sources")

    fake_query_services(retrieval=fake_retrieve, chat=chat_called)

    response = client.post("/queries", json={"question": "nothing"})

    query_id = response.json()["id"]
    detail = client.get(f"/queries/{query_id}")

    assert response.json()["answer"] == NO_SOURCES_MESSAGE
    assert detail.status_code == 200
    assert detail.json()["answer"] == NO_SOURCES_MESSAGE
    assert detail.json()["sources"] == []


def test_list_queries_returns_newest_first(client, fake_query_services):
    first = _ask(client, fake_query_services).json()
    second = _ask(client, fake_query_services).json()

    response = client.get("/queries")

    assert response.status_code == 200
    body = response.json()
    assert [q["id"] for q in body["queries"]] == [second["id"], first["id"]]
    assert body["queries"][0]["question"] == "retention period?"
    assert body["queries"][0]["created_at"] is not None


def test_get_query_returns_answer_and_sources(client, fake_query_services, tmp_path):
    _seed_library_chunk(tmp_path / "data" / "engine.db")
    query = _ask(client, fake_query_services).json()

    response = client.get(f"/queries/{query['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == query["id"]
    assert body["question"] == "retention period?"
    assert body["answer"] == "The retention policy requires 7 years."
    assert len(body["sources"]) == 1
    assert body["sources"][0]["chunk_id"] == "chunk_1"
    assert body["sources"][0]["doc_id"] == "doc_1"
    assert body["sources"][0]["doc_name"] == "notes.md"
    assert body["sources"][0]["excerpt"] == "Invoices kept 7 years."
    assert body["sources"][0]["score"] == 0.89


def test_get_query_unknown_returns_404(client):
    response = client.get("/queries/query_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "query not found"


def test_delete_query_removes_query_and_sources(client, fake_query_services):
    query = _ask(client, fake_query_services).json()

    response = client.delete(f"/queries/{query['id']}")

    assert response.status_code == 204
    assert client.get(f"/queries/{query['id']}").status_code == 404


def test_delete_query_unknown_returns_404(client):
    response = client.delete("/queries/query_missing")

    assert response.status_code == 404
