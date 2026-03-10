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

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "instance_id": self.instance_id,
            "enemy": self.enemy.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EnemyInstance":
        return cls(
            template_id=str(data.get("template_id", "")),
            instance_id=str(data.get("instance_id", "")),
            enemy=Enemy.from_dict(dict(data.get("enemy", {}))),
        )


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

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "instance_id": self.instance_id,
            "name": self.name,
            "description": self.description,
            "difficulty": self.difficulty.value,
            "clear_reward": self.clear_reward,
            "enemies": [enemy.to_dict() for enemy in self.enemies],
            "cleared": self.cleared,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterInstance":
        return cls(
            template_id=str(data.get("template_id", "")),
            instance_id=str(data.get("instance_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            difficulty=DifficultyType(str(data.get("difficulty", DifficultyType.EASY.value))),
            clear_reward=int(data.get("clear_reward", 0)),
            enemies=[EnemyInstance.from_dict(item) for item in data.get("enemies", [])],
            cleared=bool(data.get("cleared", False)),
        )


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

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "instance_id": self.instance_id,
            "name": self.name,
            "description": self.description,
            "connections": list(self.connections),
            "encounters": [encounter.to_dict() for encounter in self.encounters],
            "allowed_rests": [rest.value for rest in self.allowed_rests],
            "is_visited": self.is_visited,
            "is_cleared": self.is_cleared,
            "is_rested": self.is_rested,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoomInstance":
        return cls(
            template_id=str(data.get("template_id", "")),
            instance_id=str(data.get("instance_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            connections=[str(item) for item in data.get("connections", [])],
            encounters=[EncounterInstance.from_dict(item) for item in data.get("encounters", [])],
            allowed_rests=[RestType(str(item)) for item in data.get("allowed_rests", [])],
            is_visited=bool(data.get("is_visited", False)),
            is_cleared=bool(data.get("is_cleared", False)),
            is_rested=bool(data.get("is_rested", False)),
        )


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

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "instance_id": self.instance_id,
            "name": self.name,
            "description": self.description,
            "difficulty": self.difficulty.value,
            "start_room": self.start_room,
            "end_room": self.end_room,
            "rooms": [room.to_dict() for room in self.rooms],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DungeonInstance":
        return cls(
            template_id=str(data.get("template_id", "")),
            instance_id=str(data.get("instance_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            difficulty=DifficultyType(str(data.get("difficulty", DifficultyType.EASY.value))),
            start_room=str(data.get("start_room", "")),
            end_room=str(data.get("end_room", "")),
            rooms=[RoomInstance.from_dict(item) for item in data.get("rooms", [])],
        )
