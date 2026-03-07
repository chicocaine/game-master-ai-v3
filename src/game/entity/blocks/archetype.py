from dataclasses import dataclass, field
from typing import Any, List

from game.enums import (
	DamageType,
	ControlType,
	WeaponProficiency,
	WeaponHandling,
	WeaponWeightClass,
	WeaponDelivery,
	WeaponMagicType,
)
from game.combat_elements.attack import Attack
from game.combat_elements.spell import Spell
from game.entity.blocks.weapon import Weapon


def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))

def _get_int(value: Any) -> int:
	return int(value)

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

def _parse_weapon_proficiency(value: Any) -> WeaponProficiency:
	if isinstance(value, WeaponProficiency):
		return value
	return WeaponProficiency(str(value))

def _parse_weapon_handling(value: Any) -> WeaponHandling:
	if isinstance(value, WeaponHandling):
		return value
	return WeaponHandling(str(value))

def _parse_weapon_weight_class(value: Any) -> WeaponWeightClass:
	if isinstance(value, WeaponWeightClass):
		return value
	return WeaponWeightClass(str(value))

def _parse_weapon_delivery(value: Any) -> WeaponDelivery:
	if isinstance(value, WeaponDelivery):
		return value
	return WeaponDelivery(str(value))

def _parse_weapon_magic_type(value: Any) -> WeaponMagicType:
	if isinstance(value, WeaponMagicType):
		return value
	return WeaponMagicType(str(value))

def _parse_enum_list(value: Any, parser) -> List[Any]:
	if not isinstance(value, list):
		return []
	parsed: List[Any] = []
	for item in value:
		parsed.append(parser(item))
	return parsed


@dataclass
class WeaponConstraints:
	proficiency: List[WeaponProficiency] = field(default_factory=list)
	handling: List[WeaponHandling] = field(default_factory=list)
	weight_class: List[WeaponWeightClass] = field(default_factory=list)
	delivery: List[WeaponDelivery] = field(default_factory=list)
	magic_type: List[WeaponMagicType] = field(default_factory=list)

	def to_dict(self) -> dict:
		return {
			"proficiency": [item.value for item in self.proficiency],
			"handling": [item.value for item in self.handling],
			"weight_class": [item.value for item in self.weight_class],
			"delivery": [item.value for item in self.delivery],
			"magic_type": [item.value for item in self.magic_type],
		}

	@classmethod
	def from_dict(cls, data: Any) -> "WeaponConstraints":
		if not isinstance(data, dict):
			return cls()
		return cls(
			proficiency=_parse_enum_list(data.get("proficiency", []), _parse_weapon_proficiency),
			handling=_parse_enum_list(data.get("handling", []), _parse_weapon_handling),
			weight_class=_parse_enum_list(data.get("weight_class", []), _parse_weapon_weight_class),
			delivery=_parse_enum_list(data.get("delivery", []), _parse_weapon_delivery),
			magic_type=_parse_enum_list(data.get("magic_type", []), _parse_weapon_magic_type),
		)

@dataclass
class Archetype:
	id: str
	name: str
	description: str
	hp_mod: int
	AC_mod: int
	spell_slot_mod: int
	initiative_mod: int
	resistances: List[DamageType] = field(default_factory=list)
	immunities: List[DamageType] = field(default_factory=list)
	vulnerabilities: List[DamageType] = field(default_factory=list)
	cc_immunities: List[ControlType] = field(default_factory=list)
	weapon_constraints: WeaponConstraints = field(default_factory=WeaponConstraints)
	known_spells: List[Spell] = field(default_factory=list)
	known_attacks: List[Attack] = field(default_factory=list)

	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"description": self.description,
			"hp_mod": self.hp_mod,
			"AC_mod": self.AC_mod,
			"spell_slot_mod": self.spell_slot_mod,
			"initiative_mod": self.initiative_mod,
			"resistances": [damage_type.value for damage_type in self.resistances],
			"immunities": [damage_type.value for damage_type in self.immunities],
			"vulnerabilities": [damage_type.value for damage_type in self.vulnerabilities],
			"cc_immunities": [control_type.value for control_type in self.cc_immunities],
			"weapon_constraints": self.weapon_constraints.to_dict(),
			"known_spells": [spell.to_dict() for spell in self.known_spells],
			"known_attacks": [attack.to_dict() for attack in self.known_attacks],
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Archetype":
		return cls(
			id=_get_str(data, "id"),
			name=_get_str(data, "name"),
			description=_get_str(data, "description"),
			hp_mod=_get_int(data.get("hp_mod", 0)),
			AC_mod=_get_int(data.get("AC_mod", 0)),
			spell_slot_mod=_get_int(data.get("spell_slot_mod", 0)),
			initiative_mod=_get_int(data.get("initiative_mod", 0)),
			resistances=_parse_damage_types(data.get("resistances", [])),
			immunities=_parse_damage_types(data.get("immunities", [])),
			vulnerabilities=_parse_damage_types(data.get("vulnerabilities", [])),
			cc_immunities=_parse_control_types(data.get("cc_immunities", [])),
			weapon_constraints=WeaponConstraints.from_dict(data.get("weapon_constraints", {})),
			known_spells=_parse_known_spells(data.get("known_spells", [])),
			known_attacks=_parse_known_attacks(data.get("known_attacks", [])),
		)
