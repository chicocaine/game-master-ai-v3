from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Optional

from game.actors.enemy import Enemy
from game.enums import DifficultyType, RestType


def _get_str(data: dict, key: str) -> str:
	return str(data.get(key, ""))

def _get_int(value: Any) -> int:
	return int(value)

def _get_bool(value: Any, default: bool = False) -> bool:
	if value is None:
		return default
	return bool(value)

def _parse_difficulty_type(value: Any) -> DifficultyType:
	if isinstance(value, DifficultyType):
		return value
	return DifficultyType(str(value))

def _parse_rest_type(value: Any) -> RestType:
	if isinstance(value, RestType):
		return value
	return RestType(str(value))

def _parse_rest_type_list(value: Any) -> List[RestType]:
	if not isinstance(value, list):
		return []
	parsed_types: List[RestType] = []
	for item in value:
		parsed_types.append(_parse_rest_type(item))
	return parsed_types

def _parse_connections(value: Any) -> List[str]:
	if not isinstance(value, list):
		return []
	parsed_connections: List[str] = []
	for item in value:
		parsed_connections.append(str(item))
	return parsed_connections

def _parse_enemies(value: Any) -> List[Enemy]:
	if not isinstance(value, list):
		return []
	enemies: List[Enemy] = []
	for item in value:
		if isinstance(item, Enemy):
			enemies.append(item)
		elif isinstance(item, dict):
			enemies.append(Enemy.from_dict(item))
		elif isinstance(item, (str, int)):
			enemies.append(Enemy.from_dict({"id": str(item), "race": {}, "archetype": {}}))
	return enemies

def _parse_encounters(value: Any) -> List["Encounter"]:
	if not isinstance(value, list):
		return []

	encounters: List[Encounter] = []
	for item in value:
		if isinstance(item, Encounter):
			encounters.append(item)
		elif isinstance(item, dict):
			encounters.append(Encounter.from_dict(item))
	return encounters

def _parse_rooms(value: Any) -> List["Room"]:
	if not isinstance(value, list):
		return []

	rooms: List[Room] = []
	for item in value:
		if isinstance(item, Room):
			rooms.append(item)
		elif isinstance(item, dict):
			rooms.append(Room.from_dict(item))
	return rooms

@dataclass
class Encounter:
	id: str
	name: str
	description: str
	difficulty: DifficultyType
	cleared: bool
	clear_reward: int
	enemies: List[Enemy] = field(default_factory=list)

	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"description": self.description,
			"difficulty": self.difficulty.value,
			"cleared": self.cleared,
			"clear_reward": self.clear_reward,
			"enemies": [enemy.to_dict() for enemy in self.enemies],
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Encounter":
		return cls(
			id=_get_str(data, "id"),
			name=_get_str(data, "name"),
			description=_get_str(data, "description"),
			difficulty=_parse_difficulty_type(data.get("difficulty")),
			cleared=_get_bool(data.get("cleared"), default=False),
			clear_reward=_get_int(data.get("clear_reward", 0)),
			enemies=_parse_enemies(data.get("enemies", [])),
		)


@dataclass
class Room:
	id: str
	name: str
	description: str
	is_visited: bool
	is_cleared: bool
	is_rested: bool
	connections: List[str] = field(default_factory=list)
	encounters: List[Encounter] = field(default_factory=list)
	allowed_rests: List[RestType] = field(default_factory=list)

	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"description": self.description,
			"is_visited": self.is_visited,
			"is_cleared": self.is_cleared,
			"is_rested": self.is_rested,
			"connections": list(self.connections),
			"encounters": [encounter.to_dict() for encounter in self.encounters],
			"allowed_rests": [rest_type.value for rest_type in self.allowed_rests],
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Room":
		encounters = _parse_encounters(data.get("encounters", []))
		return cls(
			id=_get_str(data, "id"),
			name=_get_str(data, "name"),
			description=_get_str(data, "description"),
			is_visited=_get_bool(data.get("is_visited"), default=False),
			is_cleared=_get_bool(data.get("is_cleared"), default=(len(encounters) == 0)),
			is_rested=_get_bool(data.get("is_rested"), default=False),
			connections=_parse_connections(data.get("connections", [])),
			encounters=encounters,
			allowed_rests=_parse_rest_type_list(data.get("allowed_rests", [])),
		)


@dataclass
class Dungeon:
	id: str
	name: str
	description: str
	difficulty: DifficultyType
	start_room: str
	end_room: str
	rooms: List[Room] = field(default_factory=list)

	def find_room(dungeon: Dungeon, room_id: str) -> Optional[Room]:
		for room in dungeon.rooms:
			if room.id == room_id:
				return room
		return None

	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"description": self.description,
			"difficulty": self.difficulty.value,
			"start_room": self.start_room,
			"end_room": self.end_room,
			"rooms": [room.to_dict() for room in self.rooms],
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Dungeon":
		return cls(
			id=_get_str(data, "id"),
			name=_get_str(data, "name"),
			description=_get_str(data, "description"),
			difficulty=_parse_difficulty_type(data.get("difficulty")),
			start_room=_get_str(data, "start_room"),
			end_room=_get_str(data, "end_room"),
			rooms=_parse_rooms(data.get("rooms", [])),
		)
