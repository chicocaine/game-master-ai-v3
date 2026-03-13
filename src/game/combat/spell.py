from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Tuple

from game.combat.status_effect import StatusEffectInstance
from game.enums import ControlType, DamageType, SpellType, StatusEffectType


_AOE_COUNTERPARTS: dict[SpellType, SpellType] = {
    SpellType.ATTACK: SpellType.AOE_ATTACK,
    SpellType.HEAL: SpellType.AOE_HEAL,
    SpellType.BUFF: SpellType.AOE_BUFF,
    SpellType.DEBUFF: SpellType.AOE_DEBUFF,
    SpellType.CONTROL: SpellType.AOE_CONTROL,
    SpellType.CLEANSE: SpellType.AOE_CLEANSE,
}


def _parse_spell_type(value: Any) -> SpellType:
    if isinstance(value, SpellType):
        return value
    return SpellType(str(value))


def _parse_spell_types(value: Any) -> Tuple[SpellType, ...]:
    raw_values = list(value) if isinstance(value, list) else [value]
    parsed_types: list[SpellType] = []
    seen: set[SpellType] = set()
    for raw_value in raw_values:
        spell_type = _parse_spell_type(raw_value)
        if spell_type in seen:
            continue
        parsed_types.append(spell_type)
        seen.add(spell_type)
    if not parsed_types:
        raise ValueError("Spell must declare at least one spell type.")
    for single_target, aoe in _AOE_COUNTERPARTS.items():
        if single_target in seen and aoe in seen:
            raise ValueError(
                f"Spell type list cannot contain both '{single_target.value}' and '{aoe.value}'."
            )
    return tuple(parsed_types)


def _parse_damage_type(damage_type: Any) -> DamageType:
    if isinstance(damage_type, DamageType):
        return damage_type
    if damage_type in (None, ""):
        return DamageType.FORCE
    return DamageType(str(damage_type))


def _parse_damage_types(value: Any) -> List[DamageType]:
    if not isinstance(value, list):
        return []
    return [_parse_damage_type(item) for item in value]


def _parse_applied_status_effects(value: Any) -> List[StatusEffectInstance]:
    if not isinstance(value, list):
        return []
    return [StatusEffectInstance.from_dict(item) for item in value]


def _parse_status_effect_type(value: Any) -> StatusEffectType:
    if isinstance(value, StatusEffectType):
        return value
    return StatusEffectType(str(value))


def _parse_status_effect_types(value: Any) -> List[StatusEffectType]:
    if not isinstance(value, list):
        return []
    return [_parse_status_effect_type(item) for item in value]


def _parse_control_type(value: Any) -> ControlType:
    if isinstance(value, ControlType):
        return value
    return ControlType(str(value))


def _parse_control_types(value: Any) -> List[ControlType]:
    if not isinstance(value, list):
        return []
    return [_parse_control_type(item) for item in value]


def _get_str(data: dict, key: str) -> str:
    return str(data.get(key, ""))


def _get_int(value: Any) -> int:
    return int(value)


def _get_parameters(data: dict) -> Dict[str, Any]:
    params = data.get("parameters", {})
    return dict(params) if isinstance(params, dict) else {}


@dataclass(frozen=True)
class Spell:
    id: str
    name: str
    description: str
    type: Tuple[SpellType, ...] | SpellType | List[SpellType] | List[str] | str
    spell_cost: int
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _parse_spell_types(self.type))
        immutable_parameters = MappingProxyType(deepcopy(dict(self.parameters)))
        object.__setattr__(self, "parameters", immutable_parameters)

    def __deepcopy__(self, memo: dict) -> "Spell":
        return self

    @property
    def spell_types(self) -> Tuple[SpellType, ...]:
        return tuple(self.type)

    @property
    def primary_type(self) -> SpellType:
        return self.spell_types[0]

    @property
    def damage_types(self) -> List[DamageType]:
        return _parse_damage_types(self.parameters.get("damage_types", []))

    @property
    def damage_roll(self) -> str:
        return _get_str({"damage_roll": self.parameters.get("damage_roll", "0d6+0")}, "damage_roll")

    @property
    def heal_roll(self) -> str:
        return _get_str({"heal_roll": self.parameters.get("heal_roll", "0d6+0")}, "heal_roll")

    @property
    def hit_modifiers(self) -> int:
        return _get_int(self.parameters.get("hit_modifiers", 0))

    @property
    def DC(self) -> int:
        return _get_int(self.parameters.get("DC", 0))

    @property
    def applied_status_effects(self) -> List[StatusEffectInstance]:
        return _parse_applied_status_effects(self.parameters.get("applied_status_effects", []))

    @property
    def cleanse_status_effect_types(self) -> List[StatusEffectType]:
        return _parse_status_effect_types(self.parameters.get("cleanse_status_effect_types", []))

    @property
    def cleanse_control_types(self) -> List[ControlType]:
        return _parse_control_types(self.parameters.get("cleanse_control_types", []))

    def to_dict(self) -> dict:
        spell_types: str | list[str]
        if len(self.spell_types) == 1:
            spell_types = self.spell_types[0].value
        else:
            spell_types = [spell_type.value for spell_type in self.spell_types]
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": spell_types,
            "spell_cost": self.spell_cost,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Spell":
        return cls(
            id=_get_str(data, "id"),
            name=_get_str(data, "name"),
            description=_get_str(data, "description"),
            type=data.get("type"),
            spell_cost=_get_int(data.get("spell_cost", 0)),
            parameters=_get_parameters(data),
        )