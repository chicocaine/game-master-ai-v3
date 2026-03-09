from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from core.action import Action, validate_action
from core.action_result import ActionResult
from core.enums import ActionType
from game.enums import RestType
from game.runtime.models import DungeonInstance, RoomInstance

if TYPE_CHECKING:
    from game.states.game_session import GameSession


@dataclass
class ExplorationState:
    current_room: RoomInstance | None = None
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
        return not self.current_room.is_rested and len(self.current_room.allowed_rests) > 0

    # other properties of exploration

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

        target_room.is_visited = True
        self.current_room = target_room
        return ActionResult.success()

    def handle_rest(self, session: "GameSession", rest_type: RestType) -> ActionResult:
        if self.current_room is None:
            return ActionResult.failure(errors=["Cannot rest because there is no current room."])
        if not isinstance(rest_type, RestType):
            return ActionResult.failure(errors=["Invalid rest type."])
        if rest_type not in self.current_room.allowed_rests:
            return ActionResult.failure(errors=["This rest type is not allowed in the current room."])
        if self.current_room.is_rested:
            return ActionResult.failure(errors=["Current room has already been rested."])

        for player in session.party:
            if rest_type is RestType.LONG:
                player.hp = player.max_hp
                player.spell_slots = player.max_spell_slots
            if rest_type is RestType.SHORT:
                if player.hp > 0:
                    player.hp = min(player.max_hp, player.hp + max(1, player.max_hp // 2))
                player.spell_slots = min(player.max_spell_slots, player.spell_slots + max(0, player.max_spell_slots // 2))
        self.current_room.is_rested = True
        return ActionResult.success()

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
                rest_type = rest_type_value if isinstance(rest_type_value, RestType) else RestType(str(rest_type_value))
            except ValueError:
                return ActionResult.failure(errors=["Invalid rest type."])
            return self.handle_rest(session, rest_type)

        return self._unsupported_action(action)

    def to_dict(self) -> dict:
        return {
            "current_room_id": self.current_room.id if self.current_room else "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExplorationState":
        return cls(current_room=None)

    # serialization and deserialization