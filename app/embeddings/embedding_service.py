from __future__ import annotations

from typing import Any

from app.embeddings.pinecone_client import PineconeClient
from app.retry import retry_async

MODEL = "llama-text-embed-v2"
BATCH_SIZE = 32
DIMENSION = 1024

_InputType = str
INPUT_TYPE_PASSAGE = "passage"
INPUT_TYPE_QUERY = "query"


class EmbeddingServiceError(Exception):
    """Raised when embeddings cannot be produced."""


class EmbeddingService:
    def __init__(self, client: PineconeClient, sleep=None) -> None:
        self._client = client
        self._sleep = sleep

    async def embed(
        self,
        texts: list[str],
        input_type: _InputType = INPUT_TYPE_PASSAGE,
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            vectors.extend(await self._embed_batch(batch, input_type))
        return vectors

    async def _embed_batch(
        self,
        batch: list[str],
        input_type: _InputType,
    ) -> list[list[float]]:
        inference = await self._client.inference()

        async def call() -> Any:
            return await inference.embed(
                model=MODEL,
                inputs=batch,
                parameters={"input_type": input_type},
            )

        try:
            response = await retry_async(call, sleep=self._sleep)
        except Exception as exc:
            raise EmbeddingServiceError(f"embedding failed: {exc}") from exc

        return [item.values for item in response.data]
