"""DeepSeek chat completion client with retry and error mapping."""

from __future__ import annotations

from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.config import get_settings
from app.retry import retry_async


class ChatError(Exception):
    """Base error for chat completions."""


class ChatQuotaError(ChatError):
    """Raised when the quota/rate limit is hit."""


class ChatConnectionError(ChatError):
    """Raised on network/connection failures."""


def is_chat_transient(exc: Exception) -> bool:
    """Return True when a chat failure is retryable."""
    if isinstance(exc, ChatConnectionError):
        return True
    if isinstance(exc, ChatQuotaError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {408, 429, 500, 502, 503, 504}
    return False


class DeepSeekClient:
    """Async client for DeepSeek chat completions."""

    def __init__(self, client: AsyncOpenAI | None = None, model: str | None = None) -> None:
        """Wrap an existing ``AsyncOpenAI`` client, or build one from settings."""
        settings = get_settings()
        if client is not None:
            self._client = client
            self._model = model or settings.deepseek_model
            return
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self._model = settings.deepseek_model

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        sleep=None,
    ) -> str:
        """Send a chat completion and return the assistant's text.

        Raises :class:`ChatError` subclasses on failures; transient errors are
        retried with backoff. ``sleep`` is injectable for testing.
        """

        async def call() -> str:
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except APIConnectionError as exc:
                raise ChatConnectionError(f"cannot reach DeepSeek API: {exc}") from exc
            except APIStatusError as exc:
                raise _map_status_error(exc) from exc
            return _extract_content(response)

        return await retry_async(call, is_transient=is_chat_transient, sleep=sleep)


def _map_status_error(exc: APIStatusError) -> ChatError:
    """Map an OpenAI API status error to a :class:`ChatError` subtype."""
    if exc.status_code == 429:
        return ChatQuotaError(f"quota or rate limit exceeded: {exc.message}")
    return ChatError(f"chat API error {exc.status_code}: {exc.message}")


def _extract_content(response: ChatCompletion) -> str:
    """Extract the assistant message text, rejecting empty completions."""
    content = response.choices[0].message.content
    if not content:
        raise ChatError("chat completion returned empty content")
    return content
