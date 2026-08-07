import asyncio
import threading

import pytest

from app.embeddings.pinecone_client import PineconeClient, PineconeClientError, get_pinecone_client


class _FakeAsyncPinecone:
    def __init__(self, *, api_key: str):
        self.api_key = api_key
        self.closed = False
        self.inference = object()

    async def index(self, *, name: str):
        return f"index-{name}"

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_client_class(monkeypatch):
    tracker = {"count": 0, "last": None, "instances": []}

    def make_client(**kwargs):
        tracker["count"] += 1
        instance = _FakeAsyncPinecone(**kwargs)
        tracker["last"] = instance
        tracker["instances"].append(instance)
        return instance

    monkeypatch.setattr("app.embeddings.pinecone_client.AsyncPinecone", make_client)
    return tracker


async def test_index_resolves_from_settings(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="my-index")

    index = await client.index()

    assert index == "index-my-index"


async def test_index_cached_after_first_resolution(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="my-index")

    first = await client.index()
    second = await client.index()

    assert first is second


async def test_missing_api_key_raises_typed_error(fake_client_class):
    client = PineconeClient(api_key="", index_name="my-index")

    with pytest.raises(PineconeClientError, match="PINECONE_API_KEY"):
        await client.index()


async def test_missing_index_name_raises_typed_error(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="")

    with pytest.raises(PineconeClientError, match="PINECONE_INDEX"):
        await client.index()


async def test_inference_requires_key(fake_client_class):
    client = PineconeClient(api_key="", index_name="my-index")

    with pytest.raises(PineconeClientError, match="PINECONE_API_KEY"):
        await client.inference()


async def test_inference_returns_client_inference(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="my-index")

    inference = await client.inference()

    assert inference is not None


async def test_close_clears_handles(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="my-index")
    await client.index()

    await client.close()

    assert fake_client_class["count"] == 1
    assert fake_client_class["last"].closed is True


async def test_get_pinecone_client_uses_settings(monkeypatch):
    from types import SimpleNamespace

    settings = SimpleNamespace(
        pinecone_api_key="key-from-settings",
        pinecone_index="index-from-settings",
    )
    monkeypatch.setattr("app.embeddings.pinecone_client.get_settings", lambda: settings)
    get_pinecone_client.cache_clear()

    client = get_pinecone_client()

    assert client._api_key == "key-from-settings"
    assert client._index_name == "index-from-settings"
    get_pinecone_client.cache_clear()


def _index_in_own_loop(client: PineconeClient) -> None:
    asyncio.run(client.index())


async def test_index_recreated_per_event_loop(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="my-index")
    await client.index()
    assert fake_client_class["count"] == 1

    thread = threading.Thread(target=_index_in_own_loop, args=(client,))
    thread.start()
    thread.join()

    assert fake_client_class["count"] == 2
    assert fake_client_class["last"].closed is False

    await client.index()
    assert fake_client_class["count"] == 2


async def test_dead_loop_client_closed_when_reconnecting(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="my-index")

    thread = threading.Thread(target=_index_in_own_loop, args=(client,))
    thread.start()
    thread.join()

    dead = fake_client_class["instances"][0]
    assert dead.closed is False

    await client.index()

    assert dead.closed is True
    assert fake_client_class["count"] == 2


async def test_close_closes_handles_across_loops(fake_client_class):
    client = PineconeClient(api_key="secret", index_name="my-index")
    await client.index()

    thread = threading.Thread(target=_index_in_own_loop, args=(client,))
    thread.start()
    thread.join()

    await client.close()

    assert all(instance.closed for instance in fake_client_class["instances"])
