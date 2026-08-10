import pytest
from openai import APIConnectionError, APIStatusError

from app.generation.deepseek_client import (
    ChatConnectionError,
    ChatQuotaError,
    DeepSeekClient,
    is_chat_transient,
)


def _completion(content="answer text"):
    message = type("Message", (), {"content": content})
    choice = type("Choice", (), {"message": message})
    return type("ChatCompletion", (), {"choices": [choice]})


class _FakeCompletions:
    def __init__(self):
        self.calls = []
        self.result = _completion()
        self.error = None
        self.failures = 0
        self._failed = 0

    async def create(self, model, messages, extra_body):
        self.calls.append({"model": model, "messages": messages, "extra_body": extra_body})
        if self._failed < self.failures:
            self._failed += 1
            raise self.error
        return self.result


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeAsyncOpenAI:
    def __init__(self):
        self.chat = _FakeChat()


async def _no_sleep(_seconds: float) -> None:
    return None


def _client():
    fake = _FakeAsyncOpenAI()
    return DeepSeekClient(fake), fake


async def test_chat_returns_message_text():
    client, fake = _client()
    fake.chat.completions.result = _completion("The answer.")

    result = await client.chat([{"role": "user", "content": "question"}])

    assert result == "The answer."


async def test_chat_sends_model_and_non_thinking_mode():
    client, fake = _client()

    await client.chat([{"role": "user", "content": "question"}])

    call = fake.chat.completions.calls[0]
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert call["messages"] == [{"role": "user", "content": "question"}]


async def test_quota_error_raises_typed_exception():
    client, fake = _client()
    response = type("Response", (), {"status_code": 429, "headers": {}, "request": None})
    fake.chat.completions.error = APIStatusError(
        "Insufficient Balance",
        response=response,
        body=None,
    )
    fake.chat.completions.failures = 10

    with pytest.raises(ChatQuotaError):
        await client.chat([{"role": "user", "content": "question"}], sleep=_no_sleep)


async def test_connection_error_raises_typed_exception():
    client, fake = _client()
    fake.chat.completions.error = APIConnectionError(request=None)
    fake.chat.completions.failures = 10

    with pytest.raises(ChatConnectionError):
        await client.chat([{"role": "user", "content": "question"}], sleep=_no_sleep)


async def test_transient_failure_retried_then_succeeds():
    client, fake = _client()
    fake.chat.completions.error = APIConnectionError(request=None)
    fake.chat.completions.failures = 1
    fake.chat.completions.result = _completion("recovered")

    result = await client.chat([{"role": "user", "content": "q"}], sleep=_no_sleep)

    assert result == "recovered"
    assert len(fake.chat.completions.calls) == 2


async def test_persistent_transient_failure_raises_typed_error():
    client, fake = _client()
    fake.chat.completions.error = APIConnectionError(request=None)
    fake.chat.completions.failures = 10

    with pytest.raises(ChatConnectionError):
        await client.chat([{"role": "user", "content": "q"}], sleep=_no_sleep)


def test_is_chat_transient():
    assert is_chat_transient(ChatConnectionError("down")) is True
    assert is_chat_transient(ChatQuotaError("quota")) is True
    assert is_chat_transient(ValueError("bad")) is False
