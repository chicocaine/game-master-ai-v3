from dataclasses import dataclass, field
from typing import Any, Dict, List

from game.enums import AttackType, DamageType
from game.combat.status_effect import StatusEffectInstance


def _parse_attack_type(attack_type: Any) -> AttackType:
	if isinstance(attack_type, AttackType):
		return attack_type
	return AttackType(str(attack_type))

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

def _parse_applied_status_effects(value: Any) -> List[StatusEffectInstance]:
	if not isinstance(value, list):
		return []
	return [StatusEffectInstance.from_dict(item) for item in value]
    
def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))

def _get_int(value: Any) -> int:
	return int(value)

def _get_parameters(data: dict) -> Dict[str, Any]:
	params = data.get("parameters", {})
	return dict(params) if isinstance(params, dict) else {}

@dataclass
class Attack:
    id: str
    name: str
    description: str
    type: AttackType
    parameters: Dict[str, Any] = field(default_factory=dict)

    @property
    def damage_types(self) -> List[DamageType]:
        return _parse_damage_types(self.parameters.get("damage_types", []))

    @property
    def damage_roll(self) -> str:
        return _get_str({"damage_roll": self.parameters.get("damage_roll", "0d6+0")}, "damage_roll")

    @property
    def hit_modifiers(self) -> int:
        return _get_int(self.parameters.get("hit_modifiers", 0))

    @property
    def DC(self) -> int:
        return _get_int(self.parameters.get("DC", 0))

    @property
    def applied_status_effects(self) -> List[StatusEffectInstance]:
        return _parse_applied_status_effects(self.parameters.get("applied_status_effects", []))
	

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type.value,
            "parameters": dict(self.parameters),
        }
	

    @classmethod
    def from_dict(cls, data: dict) -> "Attack":
        return cls(
            id=_get_str(data, "id"),
            name=_get_str(data, "name"),
            description=_get_str(data, "description"),
            type=_parse_attack_type(data.get("type")),
            parameters=_get_parameters(data),
        )