from dataclasses import dataclass, field
from typing import Any, List

from game.enums import DamageType, ControlType
from game.combat.attack import Attack
from game.combat.spell import Spell


def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))

def _get_int(value: Any) -> int:
	return int(value)

def _parse_str_list(value: Any) -> List[str]:
	if not isinstance(value, list):
		return []
	parsed: List[str] = []
	for item in value:
		parsed.append(str(item))
	return parsed

def _parse_damage_type(value: Any) -> DamageType:
	if isinstance(value, DamageType):
		return value
	return DamageType(str(value))

def _parse_damage_types(value: Any) -> List[DamageType]:
	if not isinstance(value, list):
		return []
	parsed_types: List[DamageType] = []
	for item in value:
		parsed_types.append(_parse_damage_type(item))
	return parsed_types

def _parse_control_type(value: Any) -> ControlType:
	if isinstance(value, ControlType):
		return value
	return ControlType(str(value))

def _parse_control_types(value: Any) -> List[ControlType]:
	if not isinstance(value, list):
		return []
	parsed_types: List[ControlType] = []
	for item in value:
		parsed_types.append(_parse_control_type(item))
	return parsed_types

def _parse_known_attacks(value: Any) -> List[Attack]:
	if not isinstance(value, list):
		return []
	attacks: List[Attack] = []
	for item in value:
		if isinstance(item, Attack):
			attacks.append(item)
		elif isinstance(item, dict):
			attacks.append(Attack.from_dict(item))
	return attacks

def _parse_known_spells(value: Any) -> List[Spell]:
	if not isinstance(value, list):
		return []
	spells: List[Spell] = []
	for item in value:
		if isinstance(item, Spell):
			spells.append(item)
		elif isinstance(item, dict):
			spells.append(Spell.from_dict(item))
	return spells


@dataclass(frozen=True)
class Race:
	id: str
	name: str
	description: str
	base_hp: int
	base_AC: int
	base_spell_slots: int
	resistances: tuple[DamageType, ...] = field(default_factory=tuple)
	immunities: tuple[DamageType, ...] = field(default_factory=tuple)
	vulnerabilities: tuple[DamageType, ...] = field(default_factory=tuple)
	cc_immunities: tuple[ControlType, ...] = field(default_factory=tuple)
	archetype_constraints: tuple[str, ...] = field(default_factory=tuple)
	known_spells: tuple[Spell, ...] = field(default_factory=tuple)
	known_attacks: tuple[Attack, ...] = field(default_factory=tuple)

	def __post_init__(self) -> None:
		object.__setattr__(self, "resistances", tuple(self.resistances))
		object.__setattr__(self, "immunities", tuple(self.immunities))
		object.__setattr__(self, "vulnerabilities", tuple(self.vulnerabilities))
		object.__setattr__(self, "cc_immunities", tuple(self.cc_immunities))
		object.__setattr__(self, "archetype_constraints", tuple(self.archetype_constraints))
		object.__setattr__(self, "known_spells", tuple(self.known_spells))
		object.__setattr__(self, "known_attacks", tuple(self.known_attacks))

	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"description": self.description,
			"base_hp": self.base_hp,
			"base_AC": self.base_AC,
			"base_spell_slots": self.base_spell_slots,
			"resistances": [damage_type.value for damage_type in self.resistances],
			"immunities": [damage_type.value for damage_type in self.immunities],
			"vulnerabilities": [damage_type.value for damage_type in self.vulnerabilities],
			"cc_immunities": [control_type.value for control_type in self.cc_immunities],
			"archetype_constraints": list(self.archetype_constraints),
			"known_spells": [spell.to_dict() for spell in self.known_spells],
			"known_attacks": [attack.to_dict() for attack in self.known_attacks],
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Race":
		return cls(
			id=_get_str(data, "id"),
			name=_get_str(data, "name"),
			description=_get_str(data, "description"),
			base_hp=_get_int(data.get("base_hp", data.get("hp", 0))),
			base_AC=_get_int(data.get("base_AC", data.get("AC", 0))),
			base_spell_slots=_get_int(data.get("base_spell_slots", data.get("spell_slots", 0))),
			resistances=_parse_damage_types(data.get("resistances", [])),
			immunities=_parse_damage_types(data.get("immunities", [])),
			vulnerabilities=_parse_damage_types(data.get("vulnerabilities", [])),
			cc_immunities=_parse_control_types(data.get("cc_immunities", [])),
			archetype_constraints=_parse_str_list(data.get("archetype_constraints", [])),
			known_spells=_parse_known_spells(data.get("known_spells", [])),
			known_attacks=_parse_known_attacks(data.get("known_attacks", [])),
		)