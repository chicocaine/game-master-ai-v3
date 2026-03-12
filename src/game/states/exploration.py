from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.core.action import Action, validate_action
from game.core.action_result import ActionResult
from game.core.enums import ActionType, EventType
from game.enums import RestType
from game.runtime.models import DungeonInstance, RoomInstance

if TYPE_CHECKING:
    from game.states.game_session import GameSession


@dataclass
class ExplorationState:
    current_room: RoomInstance | None = None
    current_room_id: str = ""
    SUPPORTED_ACTIONS = {
        ActionType.MOVE,
        ActionType.REST,
    }

    @staticmethod
    def _unsupported_action(action: Action) -> ActionResult:
        return ActionResult.failure(errors=[f"Unsupported exploration action type: '{action.type.value}'."])

    @property
    def can_rest(self) -> bool:
        if self.current_room is None:
            return False
        allowed_rests = list(getattr(self.current_room, "allowed_rests", []) or [])
        return not bool(getattr(self.current_room, "is_rested", False)) and bool(allowed_rests)

    @staticmethod
    def _coerce_rest_type(value: object) -> RestType:
        if isinstance(value, RestType):
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("Invalid rest type.")
            try:
                return RestType(normalized)
            except ValueError:
                return RestType[normalized.upper()]
        raise ValueError("Invalid rest type.")

    @staticmethod
    def _find_room(dungeon: DungeonInstance, room_id: str) -> RoomInstance | None:
        for room in getattr(dungeon, "rooms", []):
            if getattr(room, "id", "") == room_id:
                return room
        return None

    def handle_move(self, session: "GameSession", target_room_id: str) -> ActionResult:
        if self.current_room is None:
            return ActionResult.failure(errors=["Cannot move because there is no current room."])
        if not target_room_id:
            return ActionResult.failure(errors=["Target room id is required."])
        if not self.current_room.is_cleared:
            return ActionResult.failure(errors=["Cannot move while current room is not cleared."])
        if target_room_id not in self.current_room.connections:
            return ActionResult.failure(errors=["Target room is not connected to the current room."])
        if getattr(session, "dungeon", None) is None:
            return ActionResult.failure(errors=["Cannot move without an active dungeon."])

        target_room = self._find_room(session.dungeon, target_room_id)
        if target_room is None:
            return ActionResult.failure(errors=["Target room does not exist in the current dungeon."])

        previous_room = self.current_room
        first_visit = not bool(getattr(target_room, "is_visited", False))
        target_room.is_visited = True
        self.current_room = target_room
        self.current_room_id = str(getattr(target_room, "id", ""))
        events = [
            {
                "type": EventType.MOVEMENT_RESOLVED.value,
                "from_room_id": str(getattr(previous_room, "id", "")),
                "to_room_id": str(getattr(target_room, "id", "")),
            },
            {
                "type": EventType.ROOM_EXITED.value,
                "room_id": str(getattr(previous_room, "id", "")),
                "room_name": str(getattr(previous_room, "name", "")),
            },
            {
                "type": EventType.ROOM_ENTERED.value,
                "room_id": str(getattr(target_room, "id", "")),
                "room_name": str(getattr(target_room, "name", "")),
            },
        ]
        if first_visit:
            events.append(
                {
                    "type": EventType.ROOM_EXPLORED.value,
                    "room_id": str(getattr(target_room, "id", "")),
                }
            )
        return ActionResult.success(events=events)

    def handle_rest(self, session: "GameSession", rest_type: RestType) -> ActionResult:
        if self.current_room is None:
            return ActionResult.failure(errors=["Cannot rest because there is no current room."])
        if not isinstance(rest_type, RestType):
            return ActionResult.failure(errors=["Invalid rest type."])
        if rest_type not in self.current_room.allowed_rests:
            return ActionResult.failure(errors=["This rest type is not allowed in the current room."])
        if self.current_room.is_rested:
            return ActionResult.failure(errors=["Current room has already been rested."])

        events = [
            {
                "type": EventType.REST_STARTED.value,
                "room_id": str(getattr(self.current_room, "id", "")),
                "rest_type": rest_type.value,
            }
        ]

        for player in session.party:
            if rest_type is RestType.LONG:
                player.hp = player.max_hp
                player.spell_slots = player.max_spell_slots
            if rest_type is RestType.SHORT:
                if player.hp > 0:
                    player.hp = min(player.max_hp, player.hp + max(1, player.max_hp // 2))
                player.spell_slots = min(player.max_spell_slots, player.spell_slots + max(0, player.max_spell_slots // 2))
        self.current_room.is_rested = True
        events.append(
            {
                "type": EventType.REST_COMPLETED.value,
                "room_id": str(getattr(self.current_room, "id", "")),
                "rest_type": rest_type.value,
            }
        )
        return ActionResult.success(events=events)

    def handle_action(self, session: "GameSession", action: Action) -> ActionResult:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        validation_errors = validate_action(action)
        if validation_errors:
            return ActionResult.failure(errors=validation_errors)

        if action.type is ActionType.MOVE:
            return self.handle_move(
                session=session,
                target_room_id=str(action.parameters.get("destination_room_id", "")),
            )

        if action.type is ActionType.REST:
            rest_type_value = action.parameters.get("rest_type")
            try:
                rest_type = self._coerce_rest_type(rest_type_value)
            except ValueError:
                return ActionResult.failure(errors=["Invalid rest type."])
            return self.handle_rest(session, rest_type)

        return self._unsupported_action(action)

    def to_dict(self) -> dict:
        room_id = self.current_room.id if self.current_room else self.current_room_id
        return {
            "current_room_id": str(room_id or ""),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExplorationState":
        room_id = str(data.get("current_room_id", "")) if isinstance(data, dict) else ""
        return cls(current_room=None, current_room_id=room_id)