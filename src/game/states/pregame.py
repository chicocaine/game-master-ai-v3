from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List

from game.core.action import Action, validate_action
from game.core.action_result import ActionResult
from game.core.enums import ActionType, EventType
from game.actors.player import PlayerInstance, create_player_instance
from game.catalog.models import DungeonTemplate
from game.runtime.models import DungeonInstance
from game.enums import GameState
from game.entity.blocks.race import Race
from game.entity.blocks.archetype import Archetype
from game.entity.blocks.weapon import Weapon

if TYPE_CHECKING:
    from game.states.game_session import GameSession



MAX_PARTY_SIZE = 4

#wala pa nahuman si pechayco
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
    def _resolve_dungeon_by_id(session: "GameSession", dungeon_id: str) -> DungeonTemplate | None:
        if not dungeon_id:
            return None
        catalog = getattr(session, "catalog", None)
        if catalog is None:
            return None
        return catalog.dungeon_templates.get(dungeon_id)

    @staticmethod
    def _materialize_dungeon_candidate(
        session: "GameSession",
        candidate: DungeonTemplate,
    ) -> tuple[DungeonInstance | None, str | None]:
        if isinstance(candidate, DungeonTemplate):
            instantiate = getattr(session, "instantiate_dungeon_template", None)
            if not callable(instantiate):
                return None, "Session does not support dungeon template instantiation."
            try:
                return instantiate(candidate), None
            except Exception as exc:  # pragma: no cover - defensive path
                return None, str(exc)
        return None, "Unsupported dungeon payload type."

    @staticmethod
    def _resolve_race(session: "GameSession", value: Any) -> tuple[Race | None, str | None]:
        if isinstance(value, Race):
            return value, None
        if isinstance(value, dict):
            try:
                return Race.from_dict(value), None
            except Exception:
                return None, "Invalid race payload."
        if isinstance(value, str):
            race_id = value.strip()
            if not race_id:
                return None, "Missing required parameter 'race' for action 'create_player'"
            catalog = getattr(session, "catalog", None)
            race_catalog = getattr(catalog, "races", None)
            if isinstance(race_catalog, dict):
                resolved = race_catalog.get(race_id)
                if isinstance(resolved, Race):
                    return resolved, None
            return None, f"Race '{race_id}' was not found in race catalog."
        return None, "Invalid race payload."

    @staticmethod
    def _resolve_archetype(session: "GameSession", value: Any) -> tuple[Archetype | None, str | None]:
        if isinstance(value, Archetype):
            return value, None
        if isinstance(value, dict):
            try:
                return Archetype.from_dict(value), None
            except Exception:
                return None, "Invalid archetype payload."
        if isinstance(value, str):
            archetype_id = value.strip()
            if not archetype_id:
                return None, "Missing required parameter 'archetype' for action 'create_player'"
            catalog = getattr(session, "catalog", None)
            archetype_catalog = getattr(catalog, "archetypes", None)
            if isinstance(archetype_catalog, dict):
                resolved = archetype_catalog.get(archetype_id)
                if isinstance(resolved, Archetype):
                    return resolved, None
            return None, f"Archetype '{archetype_id}' was not found in archetype catalog."
        return None, "Invalid archetype payload."

    @staticmethod
    def _resolve_weapons(session: "GameSession", value: Any) -> tuple[List[Weapon] | None, str | None]:
        if value is None:
            return [], None
        items: List[Any]
        if isinstance(value, list):
            items = value
        elif isinstance(value, tuple):
            items = list(value)
        else:
            items = [value]

        catalog = getattr(session, "catalog", None)
        weapon_catalog = getattr(catalog, "weapons", None)
        resolved_weapons: List[Weapon] = []
        for item in items:
            if isinstance(item, Weapon):
                resolved_weapons.append(item)
                continue
            if isinstance(item, dict):
                try:
                    resolved_weapons.append(Weapon.from_dict(item))
                except Exception:
                    return None, "Invalid weapon payload."
                continue
            if isinstance(item, str):
                weapon_id = item.strip()
                if not weapon_id:
                    return None, "Invalid weapon payload."
                if isinstance(weapon_catalog, dict):
                    resolved = weapon_catalog.get(weapon_id)
                    if isinstance(resolved, Weapon):
                        resolved_weapons.append(resolved)
                        continue
                return None, f"Weapon '{weapon_id}' was not found in weapon catalog."
            return None, "Invalid weapon payload."

        return resolved_weapons, None

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
            player: PlayerInstance = create_player_instance(
                id, name, description, race, archetype, weapons, player_instance_id,
            )
        except ValueError as exc:
            return ActionResult.failure(errors=[str(exc)])
        session.party.append(player)
        return ActionResult.success(
            events=[
                {
                    "type": EventType.PLAYER_CREATED.value,
                    "player_instance_id": player.player_instance_id,
                    "name": player.name,
                }
            ]
        )

    def handle_remove_player(self, session: "GameSession", player_instance_id: str) -> ActionResult:
        player_index = self._find_player_index(session, player_instance_id)
        if player_index < 0:
            return ActionResult.failure(errors=[f"Player '{player_instance_id}' was not found in party."])
        del session.party[player_index]
        self._compact_player_instance_ids(session)
        return ActionResult.success(
            events=[
                {
                    "type": EventType.PLAYER_REMOVED.value,
                    "player_instance_id": player_instance_id,
                }
            ]
        )

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
            replacement_player: PlayerInstance = create_player_instance(
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
        return ActionResult.success(
            events=[
                {
                    "type": EventType.PLAYER_EDITED.value,
                    "player_instance_id": player_instance_id,
                    "name": replacement_player.name,
                }
            ]
        )

    def handle_choose_dungeon(self, session: "GameSession", dungeon: DungeonInstance) -> ActionResult:
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
        return ActionResult.success(
            events=[
                {
                    "type": EventType.DUNGEON_CHOSEN.value,
                    "dungeon_id": str(getattr(dungeon, "id", "")),
                    "dungeon_name": str(getattr(dungeon, "name", "")),
                }
            ]
        )

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

        events = [
            *transition_result.events,
            {
                "type": EventType.GAME_STARTED.value,
                "party_size": len(session.party),
                "dungeon_id": str(getattr(session.dungeon, "id", "")),
            },
            {
                "type": EventType.ROOM_ENTERED.value,
                "room_id": str(getattr(start_room, "id", "")),
                "room_name": str(getattr(start_room, "name", "")),
            },
        ]
        if not bool(getattr(start_room, "is_visited", False)):
            events.append(
                {
                    "type": EventType.ROOM_EXPLORED.value,
                    "room_id": str(getattr(start_room, "id", "")),
                }
            )
            start_room.is_visited = True

        return ActionResult.success(events=events, state_changes=dict(transition_result.state_changes))

    def handle_action(self, session: "GameSession", action: Action) -> ActionResult:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        if action.type is ActionType.START:
            return self.handle_start(session)

        validation_errors = validate_action(action)
        if validation_errors:
            return ActionResult.failure(errors=validation_errors)

        if action.type is ActionType.CREATE_PLAYER:
            race, race_error = self._resolve_race(session, action.parameters.get("race"))
            if race_error:
                return ActionResult.failure(errors=[race_error])
            archetype, archetype_error = self._resolve_archetype(session, action.parameters.get("archetype"))
            if archetype_error:
                return ActionResult.failure(errors=[archetype_error])
            weapons, weapons_error = self._resolve_weapons(session, action.parameters.get("weapons", []))
            if weapons_error:
                return ActionResult.failure(errors=[weapons_error])

            return self.handle_create_player(
                session=session,
                id=str(action.parameters.get("id", action.parameters.get("name", "player"))),
                name=str(action.parameters.get("name", "")),
                description=str(action.parameters.get("description", "")),
                race=race,
                archetype=archetype,
                weapons=weapons,
            )

        if action.type is ActionType.REMOVE_PLAYER:
            return self.handle_remove_player(
                session=session,
                player_instance_id=str(action.parameters.get("player_instance_id", "")),
            )

        if action.type is ActionType.EDIT_PLAYER:
            race, race_error = self._resolve_race(session, action.parameters.get("race"))
            if race_error:
                return ActionResult.failure(errors=[race_error])
            archetype, archetype_error = self._resolve_archetype(session, action.parameters.get("archetype"))
            if archetype_error:
                return ActionResult.failure(errors=[archetype_error])
            weapons, weapons_error = self._resolve_weapons(session, action.parameters.get("weapons", []))
            if weapons_error:
                return ActionResult.failure(errors=[weapons_error])

            return self.handle_edit_player(
                session=session,
                player_instance_id=str(action.parameters.get("player_instance_id", "")),
                id=str(action.parameters.get("id", action.parameters.get("name", "player"))),
                name=str(action.parameters.get("name", "")),
                description=str(action.parameters.get("description", "")),
                race=race,
                archetype=archetype,
                weapons=weapons,
            )

        if action.type is ActionType.CHOOSE_DUNGEON:
            dungeon_id = str(action.parameters.get("dungeon", ""))
            resolved_template = self._resolve_dungeon_by_id(session, dungeon_id)
            if resolved_template is None:
                return ActionResult.failure(
                    errors=[f"Dungeon '{dungeon_id}' was not found in dungeon catalog."]
                )
            dungeon, materialize_error = self._materialize_dungeon_candidate(session, resolved_template)
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