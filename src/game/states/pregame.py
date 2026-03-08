from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from core.action import Action, validate_action
from core.enums import ActionType
from game.actors.player import Player, create_player
from game.dungeons.dungeon import Dungeon
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

    @staticmethod
    def _ok() -> List[str]:
        return []

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

    def handle_create_player(
        self,
        session: "GameSession",
        id: str,
        name: str,
        description: str,
        race: Race,
        archetype: Archetype,
        weapons: List[Weapon],
    ) -> List[str]:
        if len(session.party) >= MAX_PARTY_SIZE:
            return [f"Party is full. Maximum party size is {MAX_PARTY_SIZE}."]

        player_instance_id = self._next_player_instance_id(session)
        try:
            player: Player = create_player(
                id, name, description, race, archetype, weapons, player_instance_id,
            )
        except ValueError as exc:
            return [str(exc)]
        session.party.append(player)
        return self._ok()

    def handle_remove_player(self, session: "GameSession", player_instance_id: str) -> List[str]:
        player_index = self._find_player_index(session, player_instance_id)
        if player_index < 0:
            return [f"Player '{player_instance_id}' was not found in party."]
        del session.party[player_index]
        return self._ok()

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
    ) -> List[str]:
        player_index = self._find_player_index(session, player_instance_id)
        if player_index < 0:
            return [f"Player '{player_instance_id}' was not found in party."]

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
            return [str(exc)]
        session.party[player_index] = replacement_player
        return self._ok()

    def handle_choose_dungeon(self, session: "GameSession", dungeon: Dungeon) -> List[str]:
        errors: List[str] = []
        if dungeon is None:
            return ["Dungeon cannot be None."]
        if not dungeon.rooms:
            errors.append("Dungeon must contain at least one room.")
        if not dungeon.start_room:
            errors.append("Dungeon must define a start_room.")
        if dungeon.start_room and Dungeon.find_room(dungeon, dungeon.start_room) is None:
            errors.append("Dungeon start_room does not exist in dungeon rooms.")
        if dungeon.end_room and Dungeon.find_room(dungeon, dungeon.end_room) is None:
            errors.append("Dungeon end_room does not exist in dungeon rooms.")
        if errors:
            return errors

        session.dungeon = dungeon
        return self._ok()

    def handle_start(self, session: "GameSession") -> List[str]:
        errors: List[str] = []
        if not session.party:
            errors.append("Cannot start game without at least one player in the party.")
        if getattr(session, "dungeon", None) is None:
            errors.append("Cannot start game without selecting a dungeon.")

        if errors:
            return errors

        start_room = Dungeon.find_room(session.dungeon, session.dungeon.start_room)
        if start_room is None:
            return ["Cannot start game because dungeon start_room is invalid."]

        session.exploration.current_room = start_room
        session.state = GameState.EXPLORATION
        self.started = True
        return self._ok()

    def handle_action(self, session: "GameSession", action: Action) -> List[str]:
        if action.type is ActionType.START:
            return self.handle_start(session)

        validation_errors = validate_action(action)
        if validation_errors:
            return validation_errors

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
            dungeon = action.parameters.get("dungeon")
            if not isinstance(dungeon, Dungeon):
                return ["Choosing dungeon by id is not implemented yet. Provide a Dungeon object in parameter 'dungeon'."]
            return self.handle_choose_dungeon(session, dungeon)

        return [f"Unsupported pregame action type: '{action.type.value}'."]

    def to_dict(self) -> dict:
        return {
            "started": self.started,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PreGameState":
        return cls(started=bool(data.get("started", False)))