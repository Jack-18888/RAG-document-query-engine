import pytest

from app.retrieval.reranker import MODEL, Reranker, RerankerError, RerankResult


class _FakeRerankItem:
    def __init__(self, index, score):
        self.index = index
        self.score = score


class _FakeInference:
    def __init__(self):
        self.calls = []
        self.items = []
        self.failures = 0
        self._failed = 0

    async def rerank(
        self, model, query, documents, rank_fields, top_n, return_documents, parameters
    ):
        self.calls.append(
            {
                "model": model,
                "query": query,
                "documents": list(documents),
                "rank_fields": rank_fields,
                "top_n": top_n,
                "return_documents": return_documents,
                "parameters": parameters,
            }
        )
        if self._failed < self.failures:
            self._failed += 1
            raise TimeoutError("transient")
        return type("RerankResponse", (), {"data": self.items})


class _FakeClient:
    def __init__(self):
        self.inference_handle = _FakeInference()

    async def inference(self):
        return self.inference_handle


async def _no_sleep(_seconds: float) -> None:
    return None


def _reranker():
    client = _FakeClient()
    return Reranker(client, sleep=_no_sleep), client.inference_handle


async def test_rerank_returns_scores_in_rank_order():
    reranker, inference = _reranker()
    inference.items = [
        _FakeRerankItem(index=5, score=0.91),
        _FakeRerankItem(index=0, score=0.77),
        _FakeRerankItem(index=9, score=0.6),
    ]

    results = await reranker.rerank("question", ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"])

    assert results == [
        RerankResult(index=5, score=0.91),
        RerankResult(index=0, score=0.77),
        RerankResult(index=9, score=0.6),
    ]


async def test_rerank_sends_truncate_end_and_rank_fields():
    reranker, inference = _reranker()
    inference.items = [_FakeRerankItem(index=0, score=0.5)]

    await reranker.rerank("q", ["doc"], top_n=3)

    call = inference.calls[0]
    assert call["parameters"] == {"truncate": "END"}
    assert call["rank_fields"] == ["text"]
    assert call["model"] == MODEL
    assert call["query"] == "q"
    assert call["documents"] == ["doc"]
    assert call["top_n"] == 3
    assert call["return_documents"] is False


async def test_rerank_empty_response():
    reranker, _ = _reranker()

    results = await reranker.rerank("q", ["doc"])

    assert results == []


async def test_transient_failure_retried_and_succeeds():
    reranker, inference = _reranker()
    inference.failures = 1
    inference.items = [_FakeRerankItem(index=0, score=0.5)]

    results = await reranker.rerank("q", ["doc"])

    assert results == [RerankResult(index=0, score=0.5)]
    assert len(inference.calls) == 2


async def test_persistent_failure_raises_typed_error():
    reranker, inference = _reranker()
    inference.failures = 10

    with pytest.raises(RerankerError, match="rerank failed"):
        await reranker.rerank("q", ["doc"])
