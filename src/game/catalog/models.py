from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Tuple

from game.actors.player import PlayerInstance
from game.actors.enemy import EnemyInstance
from game.enums import DifficultyType, RestType
from game.entity.blocks.archetype import Archetype
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon


@dataclass(frozen=True)
class EnemyTemplate:
    id: str
    enemy_seed: EnemyInstance

    def __post_init__(self) -> None:
        object.__setattr__(self, "enemy_seed", deepcopy(self.enemy_seed))

    @classmethod
    def from_enemy(cls, template_id: str, enemy: EnemyInstance) -> "EnemyTemplate":
        return cls(id=template_id, enemy_seed=enemy)

    def instantiate_enemy(self) -> EnemyInstance:
        return deepcopy(self.enemy_seed)


@dataclass(frozen=True)
class PlayerTemplate:
    id: str
    player_seed: PlayerInstance

    def __post_init__(self) -> None:
        object.__setattr__(self, "player_seed", deepcopy(self.player_seed))

    @classmethod
    def from_player(cls, template_id: str, player: PlayerInstance) -> "PlayerTemplate":
        return cls(id=template_id, player_seed=player)

    def instantiate_player(self) -> PlayerInstance:
        return deepcopy(self.player_seed)


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
    player_templates: Dict[str, PlayerTemplate] = field(default_factory=dict)
    enemy_templates: Dict[str, EnemyTemplate] = field(default_factory=dict)
    dungeon_templates: Dict[str, DungeonTemplate] = field(default_factory=dict)
    races: Dict[str, Race] = field(default_factory=dict)
    archetypes: Dict[str, Archetype] = field(default_factory=dict)
    weapons: Dict[str, Weapon] = field(default_factory=dict)
