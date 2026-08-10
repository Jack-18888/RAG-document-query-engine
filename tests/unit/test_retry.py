import pytest
from pinecone.exceptions import PineconeApiException, PineconeProtocolError

from app.retry import DEFAULT_ATTEMPTS, is_transient_error, retry_async


class _FakeCounter:
    def __init__(self, failures: int, exc: Exception):
        self.failures = failures
        self.exc = exc
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return "ok"


async def _no_sleep(_seconds: float) -> None:
    return None


async def test_transient_failure_retried_then_succeeds():
    counter = _FakeCounter(2, TimeoutError("network"))

    result = await retry_async(counter, sleep=_no_sleep)

    assert result == "ok"
    assert counter.calls == 3


async def test_success_on_first_attempt():
    counter = _FakeCounter(0, TimeoutError("network"))

    result = await retry_async(counter, sleep=_no_sleep)

    assert result == "ok"
    assert counter.calls == 1


async def test_persistent_failure_raises_final_error():
    counter = _FakeCounter(10, TimeoutError("network"))

    with pytest.raises(TimeoutError):
        await retry_async(counter, sleep=_no_sleep)

    assert counter.calls == DEFAULT_ATTEMPTS


async def test_attempts_parameter_controls_retries():
    counter = _FakeCounter(10, TimeoutError("network"))

    with pytest.raises(TimeoutError):
        await retry_async(counter, attempts=2, sleep=_no_sleep)

    assert counter.calls == 2


async def test_non_transient_error_not_retried():
    counter = _FakeCounter(1, ValueError("bad input"))

    with pytest.raises(ValueError):
        await retry_async(counter, sleep=_no_sleep)

    assert counter.calls == 1


async def test_backoff_sequence(monkeypatch):
    counter = _FakeCounter(3, TimeoutError("network"))
    slept: list[float] = []

    async def record(seconds: float) -> None:
        slept.append(seconds)

    with pytest.raises(TimeoutError):
        await retry_async(counter, sleep=record)

    assert slept == [1.0, 4.0]


def test_pinecone_protocol_error_is_transient():
    assert is_transient_error(PineconeProtocolError("down")) is True


def test_pinecone_http_retryable_status_is_transient():
    exc = PineconeApiException("unavailable", status_code=503)
    assert is_transient_error(exc) is True


def test_pinecone_http_4xx_non_retryable_is_not_transient():
    exc = PineconeApiException("bad", status_code=400)
    assert is_transient_error(exc) is False


def test_value_error_is_not_transient():
    assert is_transient_error(ValueError("nope")) is False
