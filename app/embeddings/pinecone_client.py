from __future__ import annotations

from functools import lru_cache

from pinecone import AsyncPinecone

from app.config import get_settings


class PineconeClientError(Exception):
    """Raised when the Pinecone client cannot be created or connected."""


class PineconeClient:
    def __init__(self, api_key: str, index_name: str) -> None:
        self._api_key = api_key
        self._index_name = index_name
        self._client: AsyncPinecone | None = None
        self._index: object | None = None

    async def index(self) -> object:
        if self._index is not None:
            return self._index
        client = await self._connect()
        self._index = await client.index(name=self._index_name)
        return self._index

    async def inference(self) -> object:
        client = await self._connect()
        return client.inference

    async def _connect(self) -> AsyncPinecone:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise PineconeClientError(
                "PINECONE_API_KEY is not configured; add it to .env to use Pinecone"
            )
        if not self._index_name:
            raise PineconeClientError(
                "PINECONE_INDEX is not configured; add it to .env to use Pinecone"
            )
        self._client = AsyncPinecone(api_key=self._api_key)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._index = None


@lru_cache
def get_pinecone_client() -> PineconeClient:
    settings = get_settings()
    return PineconeClient(
        api_key=settings.pinecone_api_key,
        index_name=settings.pinecone_index,
    )
