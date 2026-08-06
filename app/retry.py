from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pinecone.exceptions import PineconeApiException, PineconeProtocolError

DEFAULT_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MULTIPLIER = 4.0


def is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, PineconeApiException):
        status = getattr(exc, "status_code", None)
        return status in {408, 429, 500, 502, 503, 504}
    if isinstance(exc, PineconeProtocolError):
        return True
    if isinstance(exc, OSError):
        return True
    return False


async def retry_async[T](
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    is_transient: Callable[[Exception], bool] = is_transient_error,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> T:
    if sleep is None:
        sleep = asyncio.sleep
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except Exception as exc:
            last_error = exc
            if not is_transient(exc):
                raise
            if attempt == attempts - 1:
                break
            await sleep(BACKOFF_BASE_SECONDS * BACKOFF_MULTIPLIER**attempt)
    raise last_error
