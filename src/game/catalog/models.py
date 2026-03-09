from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from game.actors.enemy import Enemy
from game.enums import DifficultyType, RestType


@dataclass(frozen=True)
class EnemyTemplate:
    id: str
    enemy: Enemy


@dataclass(frozen=True)
class EncounterTemplate:
    id: str
    name: str
    description: str
    difficulty: DifficultyType
    clear_reward: int
    enemy_template_ids: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RoomTemplate:
    id: str
    name: str
    description: str
    connections: Tuple[str, ...] = field(default_factory=tuple)
    encounters: Tuple[EncounterTemplate, ...] = field(default_factory=tuple)
    allowed_rests: Tuple[RestType, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DungeonTemplate:
    id: str
    name: str
    description: str
    difficulty: DifficultyType
    start_room: str
    end_room: str
    rooms: Tuple[RoomTemplate, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Catalog:
    enemy_templates: Dict[str, EnemyTemplate] = field(default_factory=dict)
    dungeon_templates: Dict[str, DungeonTemplate] = field(default_factory=dict)
