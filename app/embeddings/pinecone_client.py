"""Pinecone client factory that handles event-loop-bound connections."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from pinecone import AsyncPinecone
from pinecone.async_client.inference import AsyncInference
from pinecone.async_client.async_index import AsyncIndex

from app.config import get_settings


class PineconeClientError(Exception):
    """Raised when the Pinecone client cannot be created or connected."""


class PineconeClient:
    """AsyncPinecone is bound to the event loop that creates it; reusing it
    from another loop (e.g. an ingestion job's asyncio.run loop) after that
    loop closes raises "Event loop is closed". Cache one client + index per
    running loop and drop handles whose loop is closed.

    The client and index instances are intentionally returned as ``object``
    because their concrete types come from the Pinecone SDK.
    """

    def __init__(self, api_key: str, index_name: str) -> None:
        self._api_key = api_key
        self._index_name = index_name
        self._clients: dict[asyncio.AbstractEventLoop, AsyncPinecone] = {}
        self._indexes: dict[asyncio.AbstractEventLoop, AsyncIndex] = {}

    def _loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    async def index(self) -> AsyncIndex:
        """Return the index handle for the current event loop, caching it."""
        loop = self._loop()
        index = self._indexes.get(loop)
        if index is not None:
            return index
        client = await self._connect()
        self._indexes[loop] = await client.index(name=self._index_name)
        return self._indexes[loop]

    async def inference(self) -> AsyncInference:
        """Return the inference client for the current event loop."""
        client = await self._connect()
        return client.inference

    async def _connect(self) -> AsyncPinecone:
        """Connect to Pinecone for the current loop, cleaning up closed loops.

        Raises :class:`PineconeClientError` when required config is missing.
        """
        loop = self._loop()
        client = self._clients.get(loop)
        if client is not None:
            return client
        for dead in [key for key in self._clients if key.is_closed()]:
            await self._close_handle(self._clients.pop(dead))
            self._indexes.pop(dead, None)
        if not self._api_key:
            raise PineconeClientError(
                "PINECONE_API_KEY is not configured; add it to .env to use Pinecone"
            )
        if not self._index_name:
            raise PineconeClientError(
                "PINECONE_INDEX is not configured; add it to .env to use Pinecone"
            )
        client = AsyncPinecone(api_key=self._api_key)
        self._clients[loop] = client
        return client

    async def close(self) -> None:
        """Close all cached clients and clear the caches."""
        for client in list(self._clients.values()):
            await self._close_handle(client)
        self._clients.clear()
        self._indexes.clear()

    @staticmethod
    async def _close_handle(client: AsyncPinecone) -> None:
        """Best-effort close that swallows errors."""
        try:
            await client.close()
        except Exception:
            pass


@lru_cache
def get_pinecone_client() -> PineconeClient:
    """Return the process-wide Pinecone client, cached after first load."""
    settings = get_settings()
    return PineconeClient(
        api_key=settings.pinecone_api_key,
        index_name=settings.pinecone_index,
    )
