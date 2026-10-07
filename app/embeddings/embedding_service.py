"""Hosted embedding generation via Pinecone inference."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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
    """Produces dense vector embeddings for text in batches."""

    def __init__(
        self, client: PineconeClient, sleep: Callable[[float], Awaitable[None]] | None = None
    ) -> None:
        """Bind to a Pinecone client; ``sleep`` is injectable for testing."""
        self._client = client
        self._sleep = sleep

    async def embed(
        self,
        texts: list[str],
        input_type: _InputType = INPUT_TYPE_PASSAGE,
    ) -> list[list[float]]:
        """Embed ``texts`` in batches of :data:`BATCH_SIZE`.

        ``input_type`` selects the retrieval-appropriate embedding
        (:data:`INPUT_TYPE_PASSAGE` for documents, :data:`INPUT_TYPE_QUERY`
        for questions).
        """
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
        """Embed a single batch with retry, raising :class:`EmbeddingServiceError` on failure."""
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
