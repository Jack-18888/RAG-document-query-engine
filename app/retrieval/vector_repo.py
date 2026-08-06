from __future__ import annotations

from typing import Any

from app.embeddings.pinecone_client import PineconeClient
from app.retry import retry_async

UPSERT_BATCH_SIZE = 100


class VectorRepositoryError(Exception):
    """Raised when a Pinecone vector operation fails."""


class VectorRepository:
    def __init__(self, client: PineconeClient, sleep=None) -> None:
        self._client = client
        self._sleep = sleep

    async def upsert(
        self,
        chunk_ids: list[str],
        vectors: list[list[float]],
        doc_id: str,
    ) -> None:
        if len(chunk_ids) != len(vectors):
            raise VectorRepositoryError("chunk_ids and vectors must be the same length")
        index = await self._client.index()
        for start in range(0, len(chunk_ids), UPSERT_BATCH_SIZE):
            batch = [
                (
                    chunk_ids[i],
                    vectors[i],
                    {"doc_id": doc_id},
                )
                for i in range(start, min(start + UPSERT_BATCH_SIZE, len(chunk_ids)))
            ]

            async def call(batch: list[tuple[str, list[float], dict[str, str]]] = batch) -> None:
                await index.upsert(vectors=batch, namespace="")

            try:
                await retry_async(call, sleep=self._sleep)
            except Exception as exc:
                raise VectorRepositoryError(f"upsert failed: {exc}") from exc

    async def query(
        self,
        vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        index = await self._client.index()

        async def call() -> Any:
            return await index.query(
                vector=vector,
                top_k=top_k,
                namespace="",
                include_metadata=True,
            )

        try:
            response = await retry_async(call, sleep=self._sleep)
        except Exception as exc:
            raise VectorRepositoryError(f"query failed: {exc}") from exc

        results: list[dict[str, Any]] = []
        for match in response.matches:
            results.append(
                {
                    "chunk_id": match.id,
                    "score": match.score,
                    "metadata": match.metadata,
                }
            )
        return results

    async def delete_by_document(self, doc_id: str) -> None:
        index = await self._client.index()

        async def call() -> None:
            await index.delete(filter={"doc_id": doc_id}, namespace="")

        try:
            await retry_async(call, sleep=self._sleep)
        except Exception as exc:
            raise VectorRepositoryError(f"delete failed: {exc}") from exc
