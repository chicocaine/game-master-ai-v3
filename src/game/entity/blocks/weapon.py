from dataclasses import dataclass, field
from typing import Any, List

from game.enums import (
	WeaponProficiency,
	WeaponHandling,
	WeaponWeightClass,
	WeaponDelivery,
	WeaponMagicType,
)
from game.combat.attack import Attack
from game.combat.spell import Spell


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

def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))

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


@dataclass
class Weapon:
	id: str
	name: str
	description: str
	proficiency: WeaponProficiency
	handling: WeaponHandling
	weight_class: WeaponWeightClass
	delivery: WeaponDelivery
	magic_type: WeaponMagicType
	known_attacks: List[Attack] = field(default_factory=list)
	known_spells: List[Spell] = field(default_factory=list)

	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"description": self.description,
			"proficiency": self.proficiency.value,
			"handling": self.handling.value,
			"weight_class": self.weight_class.value,
			"delivery": self.delivery.value,
			"magic_type": self.magic_type.value,
			"known_attacks": [attack.to_dict() for attack in self.known_attacks],
			"known_spells": [spell.to_dict() for spell in self.known_spells],
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Weapon":
		return cls(
			id=_get_str(data, "id"),
			name=_get_str(data, "name"),
			description=_get_str(data, "description"),
			proficiency=_parse_weapon_proficiency(data.get("proficiency")),
			handling=_parse_weapon_handling(data.get("handling")),
			weight_class=_parse_weapon_weight_class(data.get("weight_class")),
			delivery=_parse_weapon_delivery(data.get("delivery")),
			magic_type=_parse_weapon_magic_type(data.get("magic_type")),
			known_attacks=_parse_known_attacks(data.get("known_attacks", [])),
			known_spells=_parse_known_spells(data.get("known_spells", [])),
		)
