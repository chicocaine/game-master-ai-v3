from dataclasses import dataclass, field
from typing import Dict, List, Set

from game.core.action import Action, validate_action
from game.core.action_result import ActionResult
from game.core.enums import ActionType, EventType

from game.enums import (
        GameState
)
from game.actors.player import PlayerInstance
from game.actors.enemy import Enemy
from game.catalog.models import Catalog, DungeonTemplate
from game.factories.instance_factory import InstanceFactory, SimpleInstanceIdGenerator
from game.runtime.models import DungeonInstance, EncounterInstance
from game.states.pregame import PreGameState
from game.states.encounter import EncounterState
from game.states.exploration import ExplorationState
from game.states.postgame import PostGameState


ALLOWED_STATE_TRANSITIONS: Dict[GameState, Set[GameState]] = {
    GameState.PREGAME: {GameState.EXPLORATION, GameState.POSTGAME},
    GameState.EXPLORATION: {GameState.ENCOUNTER, GameState.POSTGAME},
    GameState.ENCOUNTER: {GameState.EXPLORATION, GameState.POSTGAME},
    GameState.POSTGAME: set(),
}


@dataclass
class GameSession:
    state: GameState = GameState.PREGAME
    party: List[PlayerInstance] = field(default_factory=list)
    dungeon: DungeonInstance | None = None
    catalog: Catalog | None = None
    available_dungeons: List[DungeonTemplate] = field(default_factory=list)
    points: int = 0
    pregame: PreGameState = field(default_factory=PreGameState)
    exploration: ExplorationState = field(default_factory=ExplorationState)
    encounter: EncounterState = field(default_factory=EncounterState)
    postgame: PostGameState = field(default_factory=PostGameState)

    def instantiate_dungeon_template(self, template: DungeonTemplate) -> DungeonInstance:
        if self.catalog is None:
            raise ValueError("Cannot instantiate dungeon template without an attached catalog.")
        return InstanceFactory.dungeon_from_template(
            template,
            self.catalog,
            id_gen=SimpleInstanceIdGenerator(),
        )

    def reset_for_new_run(self) -> dict:
        previous_state = self.state
        self.state = GameState.PREGAME
        self.party = []
        self.dungeon = None
        self.points = 0

        if self.catalog is not None:
            self.available_dungeons = list(self.catalog.dungeon_templates.values())
        else:
            self.available_dungeons = []

        self.pregame = PreGameState()
        self.exploration = ExplorationState()
        self.encounter = EncounterState()
        self.postgame = PostGameState()

        return {
            "state": {
                "from": previous_state.value,
                "to": GameState.PREGAME.value,
            },
            "reset": {
                "fresh_pregame": True,
            },
        }

    @staticmethod
    def alive_players(players: List[PlayerInstance]) -> List[PlayerInstance]:
        return [player for player in players if player.hp > 0]

    @staticmethod
    def alive_enemies(encounter: EncounterInstance) -> List[Enemy]:
         return [enemy for enemy in encounter.enemies if enemy.hp > 0]

    def can_transition_to(self, target_state: GameState) -> bool:
        if self.state is target_state:
            return True
        return target_state in ALLOWED_STATE_TRANSITIONS.get(self.state, set())

    def transition_to(self, target_state: GameState) -> ActionResult:
        previous_state = self.state
        if self.state is target_state:
            return ActionResult.success()
        if not self.can_transition_to(target_state):
            return ActionResult.failure(
                errors=[f"Invalid state transition from '{self.state.value}' to '{target_state.value}'."]
            )
        self.state = target_state
        return ActionResult.success(
            events=[
                {
                    "type": EventType.GAME_STATE_CHANGED.value,
                    "from": previous_state.value,
                    "to": target_state.value,
                }
            ],
            state_changes={
                "state": {
                    "from": previous_state.value,
                    "to": target_state.value,
                }
            }
        )

    @staticmethod
    def _action_event_base(action: Action) -> dict:
        return {
            "action_id": action.action_id,
            "action_type": action.type.value,
            "actor_instance_id": action.actor_instance_id,
        }

    def handle_action(self, action: Action) -> ActionResult:
        base_event = self._action_event_base(action)
        lifecycle_events = [
            {
                "type": EventType.ACTION_SUBMITTED.value,
                **base_event,
            }
        ]

        validation_errors = validate_action(action)
        if validation_errors:
            lifecycle_events.append(
                {
                    "type": EventType.ACTION_REJECTED.value,
                    "reason": "validation_failed",
                    "errors": list(validation_errors),
                    **base_event,
                }
            )
            return ActionResult.failure(errors=validation_errors, events=lifecycle_events)

        lifecycle_events.append(
            {
                "type": EventType.ACTION_VALIDATED.value,
                **base_event,
            }
        )

        if action.type is ActionType.CONVERSE:
            event_message = str(action.parameters.get("message", "") or action.raw_input or "")
            return ActionResult.success(
                events=[
                    *lifecycle_events,
                    {
                        "type": EventType.CONVERSE.value,
                        "actor_instance_id": action.actor_instance_id,
                        "message": event_message,
                        "raw_input": action.raw_input,
                        "metadata": dict(action.metadata),
                    },
                    {
                        "type": EventType.ACTION_RESOLVED.value,
                        **base_event,
                    },
                ]
            )

        before_state = self.state
        if self.state is GameState.PREGAME:
            result = self.pregame.handle_action(self, action)
        elif self.state is GameState.EXPLORATION:
            result = self.exploration.handle_action(self, action)
        elif self.state is GameState.ENCOUNTER:
            result = self.encounter.handle_action(self, action)
        elif self.state is GameState.POSTGAME:
            result = self.postgame.handle_action(self, action)
        else:
            result = ActionResult.failure(errors=[f"Unsupported game state '{self.state.value}'."])

        if result.errors:
            return ActionResult.failure(
                errors=result.errors,
                events=[
                    *lifecycle_events,
                    *result.events,
                    {
                        "type": EventType.ACTION_REJECTED.value,
                        "reason": "state_handler_failed",
                        "errors": list(result.errors),
                        **base_event,
                    },
                ],
                state_changes=result.state_changes,
            )

        if self.state is not before_state and "state" not in result.state_changes:
            merged_changes = dict(result.state_changes)
            merged_changes["state"] = {
                "from": before_state.value,
                "to": self.state.value,
            }
            return ActionResult.success(
                events=[
                    *lifecycle_events,
                    *result.events,
                    {
                        "type": EventType.ACTION_RESOLVED.value,
                        **base_event,
                    },
                ],
                state_changes=merged_changes,
            )

        return ActionResult.success(
            events=[
                *lifecycle_events,
                *result.events,
                {
                    "type": EventType.ACTION_RESOLVED.value,
                    **base_event,
                },
            ],
            state_changes=result.state_changes,
        )

    def start_encounter(self, encounter: EncounterInstance) -> ActionResult:
        before_state = self.state
        if self.state is not GameState.EXPLORATION:
            return ActionResult.failure(errors=["Encounter can only start while in exploration state."])

        result = self.encounter.start_encounter(self, encounter)
        if result.errors:
            return result
        if self.state is before_state:
            return ActionResult.success(events=result.events, state_changes=result.state_changes)

        merged_state_changes = dict(result.state_changes)
        if "state" not in merged_state_changes:
            merged_state_changes["state"] = {
                "from": before_state.value,
                "to": self.state.value,
            }
        return ActionResult.success(events=result.events, state_changes=merged_state_changes)

    def start_room_encounter(self) -> ActionResult:
        if self.state is not GameState.EXPLORATION:
            return ActionResult.failure(errors=["Room encounter can only start while in exploration state."])
        if self.exploration.current_room is None:
            return ActionResult.failure(errors=["Cannot start room encounter without a current room."])

        for room_encounter in self.exploration.current_room.encounters:
            if not room_encounter.cleared:
                return self.start_encounter(room_encounter)

        return ActionResult.failure(errors=["No uncleared encounters in current room."])

    def end_encounter(self) -> ActionResult:
        before_state = self.state
        if self.state is not GameState.ENCOUNTER:
            return ActionResult.failure(errors=["Encounter can only end while in encounter state."])

        result = self.encounter.end_encounter(self)
        if result.errors:
            return result

        current_room = self.exploration.current_room
        if current_room is not None and current_room.encounters:
            current_room.is_cleared = all(room_encounter.cleared for room_encounter in current_room.encounters)

        if self.state is before_state:
            return ActionResult.success(events=result.events, state_changes=result.state_changes)

        merged_state_changes = dict(result.state_changes)
        if "state" not in merged_state_changes:
            merged_state_changes["state"] = {
                "from": before_state.value,
                "to": self.state.value,
            }
        return ActionResult.success(events=result.events, state_changes=merged_state_changes)

    @staticmethod
    def _find_room(dungeon: DungeonInstance | None, room_id: str):
        if dungeon is None or not room_id:
            return None
        for room in dungeon.rooms:
            if room.id == room_id:
                return room
        return None

    @staticmethod
    def _find_encounter(dungeon: DungeonInstance | None, encounter_id: str):
        if dungeon is None or not encounter_id:
            return None
        for room in dungeon.rooms:
            for encounter in room.encounters:
                if encounter.id == encounter_id:
                    return encounter
        return None

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "party": [player.to_dict() for player in self.party],
            "dungeon": self.dungeon.to_dict() if self.dungeon else None,
            "points": self.points,
            "available_dungeon_ids": [template.id for template in self.available_dungeons],
            "pregame": self.pregame.to_dict(),
            "exploration": self.exploration.to_dict(),
            "encounter": self.encounter.to_dict(),
            "postgame": self.postgame.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict, catalog: Catalog | None = None) -> "GameSession":
        session = cls()

        state_value = str(data.get("state", GameState.PREGAME.value))
        try:
            session.state = GameState(state_value)
        except ValueError:
            session.state = GameState.PREGAME

        party_payload = data.get("party", [])
        if isinstance(party_payload, list):
            session.party = [PlayerInstance.from_dict(item) for item in party_payload]

        dungeon_payload = data.get("dungeon")
        if isinstance(dungeon_payload, dict):
            session.dungeon = DungeonInstance.from_dict(dungeon_payload)
        else:
            session.dungeon = None

        session.points = int(data.get("points", 0))
        session.catalog = catalog

        available_ids = data.get("available_dungeon_ids", [])
        if catalog is not None and isinstance(available_ids, list) and available_ids:
            session.available_dungeons = [
                catalog.dungeon_templates[dungeon_id]
                for dungeon_id in available_ids
                if dungeon_id in catalog.dungeon_templates
            ]
        elif catalog is not None:
            session.available_dungeons = list(catalog.dungeon_templates.values())

        pregame_data = data.get("pregame", {})
        session.pregame = PreGameState.from_dict(pregame_data if isinstance(pregame_data, dict) else {})

        exploration_data = data.get("exploration", {})
        session.exploration = ExplorationState.from_dict(exploration_data if isinstance(exploration_data, dict) else {})

        encounter_data = data.get("encounter", {})
        session.encounter = EncounterState.from_dict(encounter_data if isinstance(encounter_data, dict) else {})

        postgame_data = data.get("postgame", {})
        session.postgame = PostGameState.from_dict(postgame_data if isinstance(postgame_data, dict) else {})

        # Restore runtime pointers in state objects after instances are available.
        session.exploration.current_room = cls._find_room(session.dungeon, session.exploration.current_room_id)
        if session.exploration.current_room is not None:
            session.exploration.current_room_id = str(getattr(session.exploration.current_room, "id", ""))

        encounter_id = ""
        if isinstance(encounter_data, dict):
            encounter_id = str(encounter_data.get("current_encounter_id", ""))
        session.encounter.current_encounter = cls._find_encounter(session.dungeon, encounter_id)

        return session