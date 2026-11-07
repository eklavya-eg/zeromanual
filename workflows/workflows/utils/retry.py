import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from workflows.settings import RetryPolicy

P = ParamSpec("P")
R = TypeVar("R")


class RetryExhaustedError(RuntimeError):
    def __init__(self, operation: str, attempts: int, cause: Exception) -> None:
        super().__init__(f"{operation} failed after {attempts} attempts: {cause}")
        self.operation = operation
        self.attempts = attempts
        self.cause = cause


def retry_call(
    operation: str,
    function: Callable[P, R],
    *args: P.args,
    policy: RetryPolicy,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, float, Exception], None] | None = None,
    **kwargs: P.kwargs,
) -> R:
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return function(*args, **kwargs)
        except retry_on as exc:
            if attempt == policy.max_attempts:
                raise RetryExhaustedError(operation, attempt, exc) from exc
            delay = policy.initial_delay_seconds
            if policy.strategy == "exponential":
                delay *= 2 ** (attempt - 1)
            delay = min(delay, policy.max_delay_seconds)
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            time.sleep(delay)

    raise AssertionError("retry loop ended unexpectedly")
