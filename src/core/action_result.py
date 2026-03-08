from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ActionResult:
    errors: List[str] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    state_changes: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "events": list(self.events),
            "state_changes": dict(self.state_changes),
        }

    @classmethod
    def success(
        cls,
        events: List[Dict[str, Any]] | None = None,
        state_changes: Dict[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            errors=[],
            events=list(events or []),
            state_changes=dict(state_changes or {}),
        )

    @classmethod
    def failure(
        cls,
        errors: List[str],
        events: List[Dict[str, Any]] | None = None,
        state_changes: Dict[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            errors=list(errors),
            events=list(events or []),
            state_changes=dict(state_changes or {}),
        )
