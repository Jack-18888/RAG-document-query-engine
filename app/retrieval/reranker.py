from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.embeddings.pinecone_client import PineconeClient
from app.retry import retry_async

MODEL = "bge-reranker-v2-m3"


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


class RerankerError(Exception):
    """Raised when reranking fails."""


class Reranker:
    def __init__(self, client: PineconeClient, sleep=None) -> None:
        self._client = client
        self._sleep = sleep

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 3,
    ) -> list[RerankResult]:
        inference = await self._client.inference()

        async def call() -> Any:
            return await inference.rerank(
                model=MODEL,
                query=query,
                documents=documents,
                rank_fields=["text"],
                top_n=top_n,
                return_documents=False,
                parameters={"truncate": "END"},
            )

        try:
            response = await retry_async(call, sleep=self._sleep)
        except Exception as exc:
            raise RerankerError(f"rerank failed: {exc}") from exc

        results: list[RerankResult] = []
        for item in response.data:
            results.append(RerankResult(index=item.index, score=item.score))
        return results
