class LlmError(Exception):
    """Base exception for all LLM integration failures."""


class LlmConfigurationError(LlmError):
    """Raised when LLM configuration is invalid or incomplete."""


class LlmTimeoutError(LlmError):
    """Raised when an LLM request exceeds timeout limits."""


class LlmTransportError(LlmError):
    """Raised when transport-level failures occur while calling an LLM."""


class LlmResponseParseError(LlmError):
    """Raised when model output cannot be parsed into expected JSON."""


class LlmSchemaValidationError(LlmError):
    """Raised when parsed JSON does not satisfy required payload shape."""


class LlmRetryExhaustedError(LlmError):
    """Raised when all retry attempts are consumed without success."""

    def __init__(self, message: str, attempts: int, last_error: LlmError):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error
