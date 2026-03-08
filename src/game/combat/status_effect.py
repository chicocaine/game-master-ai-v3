from dataclasses import dataclass, field
from typing import Dict, Any, List

from game.enums import StatusEffectType, DamageType, ControlType


def _parse_status_effect_type(status_effect_type: Any) -> StatusEffectType:
	if isinstance(status_effect_type, StatusEffectType):
		return status_effect_type
	return StatusEffectType(str(status_effect_type))

def _parse_damage_type(damage_type: Any) -> DamageType:
	if isinstance(damage_type, DamageType):
		return damage_type
	if damage_type in (None, ""):
		return DamageType.FORCE
	return DamageType(str(damage_type))

def _parse_damage_types(value: Any) -> List[DamageType]:
	if not isinstance(value, list):
		return []
	parsed_damage_types: List[DamageType] = []
	for item in value:
		parsed_damage_types.append(_parse_damage_type(item))
	return parsed_damage_types

def _parse_control_type(value: Any) -> ControlType:
	if isinstance(value, ControlType):
		return value
	return ControlType(str(value))

def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))

def _get_int(value: Any) -> int:
	return int(value)

def _get_parameters(data: dict) -> Dict[str, Any]:
	params = data.get("parameters", {})
	return dict(params) if isinstance(params, dict) else {}


@dataclass
class StatusEffect:
	id: str
	name: str
	description: str
	type: StatusEffectType
	parameters: Dict[str, Any] = field(default_factory=dict)

	@property
	def modifier(self) -> int:
		return _get_int(self.parameters.get("modifier", 0))

	@property
	def damage_types(self) -> List[DamageType]:
		return _parse_damage_types(self.parameters.get("damage_types", []))

	@property
	def damage_value(self) -> int:
		return _get_int(self.parameters.get("damage_value", 0))

	@property
	def heal_value(self) -> int:
		return _get_int(self.parameters.get("heal_value", 0))

	@property
	def control_type(self) -> ControlType:
		return _parse_control_type(self.parameters.get("control_type", ControlType.STUNNED))

	@property
	def immunities(self) -> List[DamageType]:
		return _parse_damage_types(self.parameters.get("damage_types", []))

	@property
	def resistances(self) -> List[DamageType]:
		return _parse_damage_types(self.parameters.get("damage_types", []))
	
	@property
	def vulnerabilities(self) -> List[DamageType]:
		return _parse_damage_types(self.parameters.get("damage_types", []))


	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"description": self.description,
			"type": self.type.value,
			"parameters": dict(self.parameters),
		}


	@classmethod
	def from_dict(cls, data: dict) -> "StatusEffect":
		return cls(
			id=_get_str(data, "id"),
			name=_get_str(data, "name"),
			description=_get_str(data, "description"),
			type=_parse_status_effect_type(data.get("type")),
			parameters=_get_parameters(data),
		)


def _parse_status_effect(value: Any) -> StatusEffect:
	if isinstance(value, StatusEffect):
		return value
	if isinstance(value, dict):
		return StatusEffect.from_dict(value)
	raise ValueError("Invalid status effect payload")


@dataclass
class StatusEffectInstance:
	status_effect: StatusEffect
	duration: int

	@classmethod
	def from_dict(cls, data: dict) -> "StatusEffectInstance":
		status_effect_payload = data.get("status_effect") if "status_effect" in data else data
		return cls(
			status_effect=_parse_status_effect(status_effect_payload),
			duration=_get_int(data.get("duration", 0)),
		)

	def tick_down(self) -> None:
		self.duration = max(self.duration - 1, 0)