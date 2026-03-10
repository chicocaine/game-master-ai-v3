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


@dataclass(frozen=True)
class LlmContextEnvelope:
    identity: Dict[str, Any]
    past_context: Dict[str, Any]
    current_context: Dict[str, Any]
    allowed_actions: List[str]
    actor_context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": dict(self.identity),
            "past_context": dict(self.past_context),
            "current_context": dict(self.current_context),
            "allowed_actions": [str(action) for action in self.allowed_actions],
            "actor_context": dict(self.actor_context),
        }
