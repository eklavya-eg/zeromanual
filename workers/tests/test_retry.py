import pytest

from workers.retry import RetryExhaustedError, retry_call
from workers.settings import RetryPolicy


def test_retry_call_retries_until_success() -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary")
        return "ok"

    result = retry_call(
        "operation",
        operation,
        policy=RetryPolicy(
            strategy="fixed",
            max_attempts=3,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        ),
        retry_on=(ConnectionError,),
    )

    assert result == "ok"
    assert attempts == 3


def test_retry_call_reports_exhaustion() -> None:
    with pytest.raises(RetryExhaustedError) as raised:
        retry_call(
            "operation",
            lambda: (_ for _ in ()).throw(ConnectionError("offline")),
            policy=RetryPolicy(
                strategy="exponential",
                max_attempts=2,
                initial_delay_seconds=0,
                max_delay_seconds=0,
            ),
            retry_on=(ConnectionError,),
        )

    assert raised.value.attempts == 2
