from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from core.action import Action, validate_action
from core.action_result import ActionResult
from core.enums import ActionType
from game.dungeons.dungeon import Dungeon, Room
from game.enums import RestType

if TYPE_CHECKING:
    from game.states.game_session import GameSession


@dataclass
class ExplorationState:
    current_room: Room | None = None
    SUPPORTED_ACTIONS = {
        ActionType.MOVE,
        ActionType.REST,
    }

    @staticmethod
    def _ok() -> List[str]:
        return []

    @staticmethod
    def _unsupported_action(action: Action) -> List[str]:
        return [f"Unsupported exploration action type: '{action.type.value}'."]

    @property
    def can_rest(self) -> bool:
        if self.current_room is None:
            return False
        return not self.current_room.is_rested and len(self.current_room.allowed_rests) > 0

    # other properties of exploration

    def handle_move(self, session: "GameSession", target_room_id: str) -> List[str]:
        if self.current_room is None:
            return ["Cannot move because there is no current room."]
        if not target_room_id:
            return ["Target room id is required."]
        if not self.current_room.is_cleared:
            return ["Cannot move while current room is not cleared."]
        if target_room_id not in self.current_room.connections:
            return ["Target room is not connected to the current room."]
        if getattr(session, "dungeon", None) is None:
            return ["Cannot move without an active dungeon."]

        target_room = Dungeon.find_room(session.dungeon, target_room_id)
        if target_room is None:
            return ["Target room does not exist in the current dungeon."]

        target_room.is_visited = True
        self.current_room = target_room
        return self._ok()

    def handle_rest(self, session: "GameSession", rest_type: RestType) -> List[str]:
        if self.current_room is None:
            return ["Cannot rest because there is no current room."]
        if not isinstance(rest_type, RestType):
            return ["Invalid rest type."]
        if rest_type not in self.current_room.allowed_rests:
            return ["This rest type is not allowed in the current room."]
        if self.current_room.is_rested:
            return ["Current room has already been rested."]

        for player in session.party:
            if rest_type is RestType.LONG:
                player.hp = player.max_hp
                player.spell_slots = player.max_spell_slots
            if rest_type is RestType.SHORT:
                if player.hp > 0:
                    player.hp = min(player.max_hp, player.hp + max(1, player.max_hp // 2))
                player.spell_slots = min(player.max_spell_slots, player.spell_slots + max(0, player.max_spell_slots // 2))
        self.current_room.is_rested = True
        return self._ok()

    def handle_action(self, session: "GameSession", action: Action) -> List[str]:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        validation_errors = validate_action(action)
        if validation_errors:
            return validation_errors

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
                return ["Invalid rest type."]
            return self.handle_rest(session, rest_type)

        return self._unsupported_action(action)

    def handle_action_result(self, session: "GameSession", action: Action) -> ActionResult:
        errors = self.handle_action(session, action)
        if errors:
            return ActionResult.failure(errors=errors)
        return ActionResult.success()

    def to_dict(self) -> dict:
        return {
            "current_room_id": self.current_room.id if self.current_room else "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExplorationState":
        return cls(current_room=None)

    # serialization and deserialization