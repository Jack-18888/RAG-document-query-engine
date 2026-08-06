import pytest

from app.embeddings.embedding_service import (
    BATCH_SIZE,
    INPUT_TYPE_PASSAGE,
    INPUT_TYPE_QUERY,
    EmbeddingService,
    EmbeddingServiceError,
)
from app.retry import is_transient_error


class _FakeInference:
    def __init__(self):
        self.calls: list[dict] = []
        self.failures_before_success = 0
        self._fails = 0

    async def embed(self, model, inputs, parameters):
        self.calls.append({"model": model, "inputs": list(inputs), "parameters": parameters})
        if self._fails < self.failures_before_success:
            self._fails += 1
            raise TimeoutError("transient network failure")
        return _FakeEmbeddings([_dense(i, len(inputs)) for i in range(len(inputs))])


def _dense(index, total):
    return {"values": [float(index), float(total)], "vector_type": "dense"}


class _FakeEmbeddings:
    def __init__(self, data):
        self.data = [type("Embedding", (), {"values": item["values"]}) for item in data]


class _FakeClient:
    def __init__(self):
        self.inference_handle = _FakeInference()

    async def inference(self):
        return self.inference_handle


async def _no_sleep(_seconds: float) -> None:
    return None


def _service():
    return EmbeddingService(_FakeClient(), sleep=_no_sleep)


async def test_embed_returns_one_vector_per_input():
    service = _service()

    vectors = await service.embed(["a", "b", "c"])

    assert len(vectors) == 3
    for v in vectors:
        assert isinstance(v, list)
        assert all(isinstance(x, float) for x in v)


async def test_embed_sets_passage_input_type_by_default():
    service = _service()
    await service.embed(["hello"])

    call = service._client.inference_handle.calls[0]
    assert call["parameters"]["input_type"] == INPUT_TYPE_PASSAGE
    assert call["model"] == "llama-text-embed-v2"


async def test_embed_accepts_query_input_type():
    service = _service()
    await service.embed(["question"], INPUT_TYPE_QUERY)

    call = service._client.inference_handle.calls[0]
    assert call["parameters"]["input_type"] == INPUT_TYPE_QUERY


async def test_embed_batches_at_32_and_preserves_order():
    service = _service()
    texts = [f"text-{i}" for i in range(70)]

    vectors = await service.embed(texts)

    calls = service._client.inference_handle.calls
    assert len(calls) == 3
    assert [len(c["inputs"]) for c in calls] == [32, 32, 6]
    assert calls[0]["inputs"] == texts[0:32]
    assert calls[1]["inputs"] == texts[32:64]
    assert calls[2]["inputs"] == texts[64:70]
    assert len(vectors) == 70


async def test_transient_failure_retried_and_succeeds(monkeypatch):
    service = _service()
    service._client.inference_handle.failures_before_success = 1

    vectors = await service.embed(["hello"])

    assert len(vectors) == 1
    assert len(service._client.inference_handle.calls) == 2


async def test_persistent_failure_raises_typed_error(monkeypatch):
    service = _service()
    service._client.inference_handle.failures_before_success = 10

    with pytest.raises(EmbeddingServiceError, match="embedding failed"):
        await service.embed(["hello"])


def test_timeout_is_transient():
    assert is_transient_error(TimeoutError()) is True


def test_embed_batch_size_constant():
    assert BATCH_SIZE == 32
