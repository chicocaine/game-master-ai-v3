from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from core.enums import EventType


def _get_str(data: dict, key: str, default: str = "") -> str:
	return str(data.get(key, default))

def _get_dict(data: dict, key: str) -> Dict[str, Any]:
	value = data.get(key, {})
	if isinstance(value, dict):
		return value
	return {}

def _utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


@dataclass
class Event:
	type: EventType
	name: str
	payload: Dict[str, Any] = field(default_factory=dict)
	source: str = "engine"
	timestamp: str = field(default_factory=_utc_now_iso)
	event_id: str = field(default_factory=lambda: str(uuid4()))

	def to_dict(self) -> dict:
		return {
			"event_id": self.event_id,
			"type": self.type.value,
			"name": self.name,
			"source": self.source,
			"timestamp": self.timestamp,
			"payload": self.payload,
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Event":
		return cls(
			type=EventType(_get_str(data, "type", EventType.SYSTEM_MESSAGE.value)),
			name=_get_str(data, "name"),
			payload=_get_dict(data, "payload"),
			source=_get_str(data, "source", "engine"),
			timestamp=_get_str(data, "timestamp", _utc_now_iso()),
			event_id=_get_str(data, "event_id", str(uuid4())),
		)

	@classmethod
	def narration(cls, message: str, source: str = "gm", **extra_payload: Any) -> "Event":
		payload = {"message": message}
		payload.update(extra_payload)
		return cls(type=EventType.NARRATION, name="narration", payload=payload, source=source)

	@classmethod
	def state_update(
		cls,
		event_type: EventType,
		name: str,
		target_id: str,
		changes: Dict[str, Any],
		source: str = "engine",
		**extra_payload: Any,
	) -> "Event":
		payload: Dict[str, Any] = {"target_id": target_id, "changes": changes}
		payload.update(extra_payload)
		return cls(type=event_type, name=name, payload=payload, source=source)


def create_event(
	event_type: EventType,
	name: str,
	payload: Dict[str, Any] | None = None,
	source: str = "engine",
) -> Event:
	return Event(
		type=event_type,
		name=name,
		payload=payload or {},
		source=source,
	)
