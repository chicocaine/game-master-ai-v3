from dataclasses import dataclass
import time
from typing import Callable, Protocol

from game.llm.contracts import LlmRequest, LlmResponse
from game.llm.errors import (
    LlmError,
    LlmRetryExhaustedError,
    LlmTimeoutError,
    LlmTransportError,
)


class LlmClient(Protocol):
    def complete(self, request: LlmRequest) -> LlmResponse:
        """Execute one LLM completion request."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    backoff_seconds: float = 0.0


def normalize_client_exception(exc: Exception) -> LlmError:
    if isinstance(exc, LlmError):
        return exc
    if isinstance(exc, TimeoutError):
        return LlmTimeoutError(str(exc) or "LLM request timed out")
    return LlmTransportError(str(exc) or "LLM transport failure")


def is_retriable_error(err: LlmError) -> bool:
    return isinstance(err, (LlmTimeoutError, LlmTransportError))


def invoke_with_retry(
    client: LlmClient,
    request: LlmRequest,
    retry_policy: RetryPolicy | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> LlmResponse:
    policy = retry_policy or RetryPolicy()
    if policy.max_attempts <= 0:
        raise ValueError("RetryPolicy.max_attempts must be > 0")
    if policy.backoff_seconds < 0:
        raise ValueError("RetryPolicy.backoff_seconds must be >= 0")

    attempts = 0
    last_error: LlmError | None = None

    while attempts < policy.max_attempts:
        attempts += 1
        try:
            return client.complete(request)
        except Exception as exc:
            mapped_error = normalize_client_exception(exc)
            last_error = mapped_error

            should_retry = attempts < policy.max_attempts and is_retriable_error(mapped_error)
            if not should_retry:
                if attempts >= policy.max_attempts:
                    break
                raise mapped_error

            if policy.backoff_seconds > 0:
                sleep_fn(policy.backoff_seconds)

    if last_error is None:
        raise LlmRetryExhaustedError("LLM call failed with no captured error.", attempts=attempts, last_error=LlmTransportError("unknown"))

    raise LlmRetryExhaustedError(
        f"LLM call failed after {attempts} attempt(s).",
        attempts=attempts,
        last_error=last_error,
    )
