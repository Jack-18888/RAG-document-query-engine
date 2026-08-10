import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class _FakeIndex:
    async def upsert(self, **kwargs):
        return None

    async def query(self, **kwargs):
        return type("QueryResponse", (), {"matches": []})

    async def delete(self, **kwargs):
        return None


class _FakeClient:
    def __init__(self):
        self.index_handle = _FakeIndex()

    async def index(self):
        return self.index_handle

    async def inference(self):
        raise AssertionError("inference should not be called in API tests")


@pytest.fixture
def fake_pinecone(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr("app.embeddings.pinecone_client.get_pinecone_client", lambda: client)
    return client


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


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "engine.db"
    monkeypatch.setattr(
        "app.storage.db.get_settings",
        lambda: type("S", (), {"database_path": str(db_path)})(),
    )
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: type(
            "S",
            (),
            {
                "database_path": str(db_path),
                "upload_dir": str(tmp_path / "uploads"),
                "job_max_workers": 1,
                "max_upload_size_mb": 1,
                "deepseek_model": "deepseek-v4-flash",
                "deepseek_base_url": "https://api.deepseek.com",
                "deepseek_api_key": "test-key",
            },
        )(),
    )
    monkeypatch.setattr(
        "app.api.documents.get_settings",
        lambda: type(
            "S",
            (),
            {
                "upload_dir": str(tmp_path / "uploads"),
                "max_upload_size_mb": 1,
            },
        )(),
    )

    with TestClient(create_app()) as test_client:
        yield test_client
