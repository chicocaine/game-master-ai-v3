from __future__ import annotations

from typing import Protocol, runtime_checkable

from game.enums import RestType


@runtime_checkable
class EnemyLike(Protocol):
    enemy_instance_id: str
    hp: int


@runtime_checkable
class EncounterLike(Protocol):
    id: str
    enemies: list[EnemyLike]
    cleared: bool
    clear_reward: int


@runtime_checkable
class RoomLike(Protocol):
    id: str
    connections: list[str]
    encounters: list[EncounterLike]
    allowed_rests: list[RestType]
    is_visited: bool
    is_cleared: bool
    is_rested: bool


@runtime_checkable
class DungeonLike(Protocol):
    id: str
    start_room: str
    end_room: str
    rooms: list[RoomLike]
