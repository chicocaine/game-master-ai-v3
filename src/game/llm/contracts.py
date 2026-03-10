from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class LlmMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LlmRequest:
    model: str
    messages: List[LlmMessage]
    temperature: float
    max_tokens: int
    timeout_seconds: int
    response_format: Dict[str, Any] | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LlmResponse:
    text: str
    finish_reason: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)
