from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from game.combat.status_effect import StatusEffectInstance
from game.enums import DifficultyType, RestType


@dataclass
class EnemyInstance:
    template_id: str
    instance_id: str
    name: str
    description: str
    hp: int
    max_hp: int
    base_AC: int
    AC: int
    spell_slots: int
    max_spell_slots: int
    initiative_mod: int
    attack_modifier_bonus: int
    persona: str
    active_status_effects: List[StatusEffectInstance] = field(default_factory=list)


@dataclass
class EncounterInstance:
    template_id: str
    instance_id: str
    name: str
    description: str
    difficulty: DifficultyType
    clear_reward: int
    enemies: List[EnemyInstance] = field(default_factory=list)
    cleared: bool = False


@dataclass
class RoomInstance:
    template_id: str
    instance_id: str
    name: str
    description: str
    connections: List[str] = field(default_factory=list)
    encounters: List[EncounterInstance] = field(default_factory=list)
    allowed_rests: List[RestType] = field(default_factory=list)
    is_visited: bool = False
    is_cleared: bool = False
    is_rested: bool = False


@dataclass
class DungeonInstance:
    template_id: str
    instance_id: str
    name: str
    description: str
    difficulty: DifficultyType
    start_room: str
    end_room: str
    rooms: List[RoomInstance] = field(default_factory=list)
