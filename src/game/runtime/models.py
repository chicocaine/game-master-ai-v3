from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from game.actors.enemy import Enemy
from game.combat.status_effect import StatusEffectInstance
from game.enums import DifficultyType, RestType


@dataclass
class EnemyInstance:
    template_id: str
    instance_id: str
    enemy: Enemy

    @property
    def id(self) -> str:
        return self.template_id

    @property
    def enemy_instance_id(self) -> str:
        return self.enemy.enemy_instance_id

    @enemy_instance_id.setter
    def enemy_instance_id(self, value: str) -> None:
        self.enemy.enemy_instance_id = value

    @property
    def hp(self) -> int:
        return self.enemy.hp

    @hp.setter
    def hp(self, value: int) -> None:
        self.enemy.hp = value

    @property
    def active_status_effects(self) -> List[StatusEffectInstance]:
        return self.enemy.active_status_effects

    @property
    def persona(self) -> str:
        return self.enemy.persona

    def __getattr__(self, name: str):
        # Delegate combat-facing attributes (AC, merged_* properties, known_* lists, etc.).
        return getattr(self.enemy, name)


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

    @property
    def id(self) -> str:
        return self.template_id


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

    @property
    def id(self) -> str:
        return self.template_id


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

    @property
    def id(self) -> str:
        return self.template_id
