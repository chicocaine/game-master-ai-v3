from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple

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


def _primary_damage_type(effect: StatusEffect) -> DamageType:
	damage_types = effect.damage_types
	if not damage_types:
		return DamageType.FORCE
	return damage_types[0]


def _overwrite_key(effect: StatusEffect) -> Tuple[str, ...] | None:
	effect_type = effect.type
	if effect_type is StatusEffectType.ATKMOD:
		return (effect_type.value,)
	if effect_type is StatusEffectType.ACMOD:
		return None
	if effect_type in (StatusEffectType.DOT, StatusEffectType.HOT):
		return (effect_type.value, _primary_damage_type(effect).value)
	if effect_type is StatusEffectType.CONTROL:
		return (effect_type.value, effect.control_type.value)
	if effect_type in {
		StatusEffectType.CC_IMMUNITY,
		StatusEffectType.IMMUNITY,
		StatusEffectType.RESISTANCE,
		StatusEffectType.VULNERABLE,
	}:
		return (effect_type.value,)
	return None


def apply_status_effect_instances(
	target_effects: List[StatusEffectInstance],
	incoming_effects: List[StatusEffectInstance],
) -> int:
	"""Apply status effects using stack/overwrite mechanics.

	Returns the number of incoming effects that were applied (added or overwritten).
	"""
	if not incoming_effects:
		return 0

	applied_count = 0
	for incoming in incoming_effects:
		if incoming.duration <= 0:
			continue

		incoming_key = _overwrite_key(incoming.status_effect)
		if incoming_key is None:
			target_effects.append(incoming)
			applied_count += 1
			continue

		replaced = False
		for index, existing in enumerate(target_effects):
			if existing.duration <= 0:
				continue
			existing_key = _overwrite_key(existing.status_effect)
			if existing_key == incoming_key:
				target_effects[index] = incoming
				replaced = True
				break

		if not replaced:
			target_effects.append(incoming)
		applied_count += 1

	return applied_count


def total_attack_modifier_from_effects(effects: List[StatusEffectInstance]) -> int:
	return sum(
		effect.status_effect.modifier
		for effect in effects
		if effect.duration > 0 and effect.status_effect.type is StatusEffectType.ATKMOD
	)


def total_ac_modifier_from_effects(effects: List[StatusEffectInstance]) -> int:
	return sum(
		effect.status_effect.modifier
		for effect in effects
		if effect.duration > 0 and effect.status_effect.type is StatusEffectType.ACMOD
	)


def merged_damage_affinities_from_effects(
	effects: List[StatusEffectInstance],
) -> tuple[List[DamageType], List[DamageType], List[DamageType]]:
	immunities: List[DamageType] = []
	resistances: List[DamageType] = []
	vulnerabilities: List[DamageType] = []

	for effect in effects:
		if effect.duration <= 0:
			continue
		effect_type = effect.status_effect.type
		if effect_type is StatusEffectType.IMMUNITY:
			immunities.extend(effect.status_effect.immunities)
		elif effect_type is StatusEffectType.RESISTANCE:
			resistances.extend(effect.status_effect.resistances)
		elif effect_type is StatusEffectType.VULNERABLE:
			vulnerabilities.extend(effect.status_effect.vulnerabilities)

	return (
		sorted(list(set(immunities)), key=lambda x: x.value),
		sorted(list(set(resistances)), key=lambda x: x.value),
		sorted(list(set(vulnerabilities)), key=lambda x: x.value),
	)


def merged_control_immunities_from_effects(effects: List[StatusEffectInstance]) -> List[ControlType]:
	control_immunities: List[ControlType] = []
	for effect in effects:
		if effect.duration <= 0:
			continue
		if effect.status_effect.type is StatusEffectType.CC_IMMUNITY:
			control_immunities.append(effect.status_effect.control_type)
	return sorted(list(set(control_immunities)), key=lambda x: x.value)


def tick_and_prune_status_effects(effects: List[StatusEffectInstance]) -> int:
	"""Decrement duration for active effects and remove expired effects.

	Returns the number of effects removed due to expiry.
	"""
	for effect in effects:
		if effect.duration > 0:
			effect.tick_down()

	remaining = [effect for effect in effects if effect.duration > 0]
	removed_count = len(effects) - len(remaining)
	effects[:] = remaining
	return removed_count