from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List

from core.action import Action, validate_action
from core.action_result import ActionResult
from core.enums import ActionType
from game.actors.player import Player, create_player
from game.catalog.models import DungeonTemplate
from game.dungeons.dungeon import Dungeon
from game.runtime.models import DungeonInstance
from game.enums import GameState
from game.entity.blocks.race import Race
from game.entity.blocks.archetype import Archetype
from game.entity.blocks.weapon import Weapon

if TYPE_CHECKING:
    from game.states.game_session import GameSession



MAX_PARTY_SIZE = 4


@dataclass
class PreGameState:
    started: bool = False
    SUPPORTED_ACTIONS = {
        ActionType.START,
        ActionType.CREATE_PLAYER,
        ActionType.REMOVE_PLAYER,
        ActionType.EDIT_PLAYER,
        ActionType.CHOOSE_DUNGEON,
    }

    @staticmethod
    def _unsupported_action(action: Action) -> ActionResult:
        return ActionResult.failure(errors=[f"Unsupported pregame action type: '{action.type.value}'."])

    @staticmethod
    def _find_room(dungeon: Any, room_id: str) -> Any | None:
        for room in getattr(dungeon, "rooms", []):
            if getattr(room, "id", "") == room_id:
                return room
        return None

    @staticmethod
    def _resolve_dungeon_by_id(session: "GameSession", dungeon_id: str) -> Dungeon | DungeonTemplate | DungeonInstance | None:
        if not dungeon_id:
            return None

        dungeon_catalog = getattr(session, "dungeon_catalog", None)
        if isinstance(dungeon_catalog, dict):
            candidate = dungeon_catalog.get(dungeon_id)
            if isinstance(candidate, (Dungeon, DungeonTemplate, DungeonInstance)):
                return candidate

        available_dungeons = getattr(session, "available_dungeons", None)
        if isinstance(available_dungeons, list):
            for dungeon in available_dungeons:
                if isinstance(dungeon, (Dungeon, DungeonTemplate, DungeonInstance)) and dungeon.id == dungeon_id:
                    return dungeon

        dungeons = getattr(session, "dungeons", None)
        if isinstance(dungeons, list):
            for dungeon in dungeons:
                if isinstance(dungeon, (Dungeon, DungeonTemplate, DungeonInstance)) and dungeon.id == dungeon_id:
                    return dungeon

        return None

    @staticmethod
    def _materialize_dungeon_candidate(
        session: "GameSession",
        candidate: Any,
    ) -> tuple[Dungeon | None, str | None]:
        if isinstance(candidate, Dungeon):
            return candidate, None

        if isinstance(candidate, DungeonInstance):
            return candidate, None

        if isinstance(candidate, DungeonTemplate):
            instantiate = getattr(session, "instantiate_dungeon_template", None)
            if not callable(instantiate):
                return None, "Session does not support dungeon template instantiation."
            try:
                return instantiate(candidate), None
            except Exception as exc:  # pragma: no cover - defensive path
                return None, str(exc)

        return None, "Unsupported dungeon payload type."

    def _next_player_instance_id(self, session: "GameSession") -> str:
        used_ids = {player.player_instance_id for player in session.party if player.player_instance_id}
        index = 1
        while f"player_{index}" in used_ids:
            index += 1
        return f"player_{index}"

    def _find_player_index(self, session: "GameSession", player_instance_id: str) -> int:
        for index, player in enumerate(session.party):
            if player.player_instance_id == player_instance_id:
                return index
        return -1

    @staticmethod
    def _compact_player_instance_ids(session: "GameSession") -> None:
        for index, player in enumerate(session.party, start=1):
            player.player_instance_id = f"player_{index}"

    def handle_create_player(
        self,
        session: "GameSession",
        id: str,
        name: str,
        description: str,
        race: Race,
        archetype: Archetype,
        weapons: List[Weapon],
    ) -> ActionResult:
        if len(session.party) >= MAX_PARTY_SIZE:
            return ActionResult.failure(errors=[f"Party is full. Maximum party size is {MAX_PARTY_SIZE}."])

        player_instance_id = self._next_player_instance_id(session)
        try:
            player: Player = create_player(
                id, name, description, race, archetype, weapons, player_instance_id,
            )
        except ValueError as exc:
            return ActionResult.failure(errors=[str(exc)])
        session.party.append(player)
        return ActionResult.success()

    def handle_remove_player(self, session: "GameSession", player_instance_id: str) -> ActionResult:
        player_index = self._find_player_index(session, player_instance_id)
        if player_index < 0:
            return ActionResult.failure(errors=[f"Player '{player_instance_id}' was not found in party."])
        del session.party[player_index]
        self._compact_player_instance_ids(session)
        return ActionResult.success()

    def handle_edit_player(
        self,
        session: "GameSession",
        player_instance_id: str,
        id: str,
        name: str,
        description: str,
        race: Race,
        archetype: Archetype,
        weapons: List[Weapon],
    ) -> ActionResult:
        player_index = self._find_player_index(session, player_instance_id)
        if player_index < 0:
            return ActionResult.failure(errors=[f"Player '{player_instance_id}' was not found in party."])

        try:
            replacement_player: Player = create_player(
                id,
                name,
                description,
                race,
                archetype,
                weapons,
                player_instance_id,
            )
        except ValueError as exc:
            return ActionResult.failure(errors=[str(exc)])
        session.party[player_index] = replacement_player
        return ActionResult.success()

    def handle_choose_dungeon(self, session: "GameSession", dungeon: Dungeon | DungeonInstance) -> ActionResult:
        errors: List[str] = []
        if dungeon is None:
            return ActionResult.failure(errors=["Dungeon cannot be None."])
        if not dungeon.rooms:
            errors.append("Dungeon must contain at least one room.")
        if not dungeon.start_room:
            errors.append("Dungeon must define a start_room.")
        if dungeon.start_room and self._find_room(dungeon, dungeon.start_room) is None:
            errors.append("Dungeon start_room does not exist in dungeon rooms.")
        if dungeon.end_room and self._find_room(dungeon, dungeon.end_room) is None:
            errors.append("Dungeon end_room does not exist in dungeon rooms.")
        if errors:
            return ActionResult.failure(errors=errors)

        session.dungeon = dungeon
        return ActionResult.success()

    def handle_start(self, session: "GameSession") -> ActionResult:
        errors: List[str] = []
        if not session.party:
            errors.append("Cannot start game without at least one player in the party.")
        if getattr(session, "dungeon", None) is None:
            errors.append("Cannot start game without selecting a dungeon.")

        if errors:
            return ActionResult.failure(errors=errors)

        start_room = self._find_room(session.dungeon, session.dungeon.start_room)
        if start_room is None:
            return ActionResult.failure(errors=["Cannot start game because dungeon start_room is invalid."])

        session.exploration.current_room = start_room
        if hasattr(session, "transition_to"):
            transition_result = session.transition_to(GameState.EXPLORATION)
        else:
            session.state = GameState.EXPLORATION
            transition_result = ActionResult.success()
        if transition_result.errors:
            return transition_result
        self.started = True
        return ActionResult.success()

    def handle_action(self, session: "GameSession", action: Action) -> ActionResult:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        if action.type is ActionType.START:
            return self.handle_start(session)

        validation_errors = validate_action(action)
        if validation_errors:
            return ActionResult.failure(errors=validation_errors)

        if action.type is ActionType.CREATE_PLAYER:
            return self.handle_create_player(
                session=session,
                id=str(action.parameters.get("id", action.parameters.get("name", "player"))),
                name=str(action.parameters.get("name", "")),
                description=str(action.parameters.get("description", "")),
                race=action.parameters.get("race"),
                archetype=action.parameters.get("archetype"),
                weapons=action.parameters.get("weapons", []),
            )

        if action.type is ActionType.REMOVE_PLAYER:
            return self.handle_remove_player(
                session=session,
                player_instance_id=str(action.parameters.get("player_instance_id", "")),
            )

        if action.type is ActionType.EDIT_PLAYER:
            return self.handle_edit_player(
                session=session,
                player_instance_id=str(action.parameters.get("player_instance_id", "")),
                id=str(action.parameters.get("id", action.parameters.get("name", "player"))),
                name=str(action.parameters.get("name", "")),
                description=str(action.parameters.get("description", "")),
                race=action.parameters.get("race"),
                archetype=action.parameters.get("archetype"),
                weapons=action.parameters.get("weapons", []),
            )

        if action.type is ActionType.CHOOSE_DUNGEON:
            dungeon_param = action.parameters.get("dungeon")
            if isinstance(dungeon_param, (Dungeon, DungeonTemplate)):
                dungeon, materialize_error = self._materialize_dungeon_candidate(session, dungeon_param)
                if materialize_error:
                    return ActionResult.failure(errors=[materialize_error])
            else:
                dungeon_id = str(dungeon_param)
                resolved_candidate = self._resolve_dungeon_by_id(session, dungeon_id)
                if resolved_candidate is None:
                    return ActionResult.failure(
                        errors=[f"Dungeon '{dungeon_id}' was not found in available dungeon catalog."]
                    )
                dungeon, materialize_error = self._materialize_dungeon_candidate(session, resolved_candidate)
                if materialize_error:
                    return ActionResult.failure(errors=[materialize_error])
            return self.handle_choose_dungeon(session, dungeon)

        return self._unsupported_action(action)

    def to_dict(self) -> dict:
        return {
            "started": self.started,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PreGameState":
        return cls(started=bool(data.get("started", False)))