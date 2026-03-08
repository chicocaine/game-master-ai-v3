from dataclasses import dataclass, field
from typing import Dict, List, Set

from core.action import Action, validate_action
from core.action_result import ActionResult
from core.enums import ActionType, EventType

from game.enums import (
        GameState
)
from game.actors.player import Player
from game.actors.enemy import Enemy
from game.dungeons.dungeon import Dungeon, Encounter
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
    party: List[Player] = field(default_factory=list)
    dungeon: Dungeon | None = None
    points: int = 0
    pregame: PreGameState = field(default_factory=PreGameState)
    exploration: ExplorationState = field(default_factory=ExplorationState)
    encounter: EncounterState = field(default_factory=EncounterState)
    postgame: PostGameState = field(default_factory=PostGameState)

    def alive_players(players: List[Player]) -> List[Player]:
        return [player for player in players if player.hp > 0]
    
    def alive_enemies(encounter: Encounter) -> List[Enemy]:
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
            state_changes={
                "state": {
                    "from": previous_state.value,
                    "to": target_state.value,
                }
            }
        )

    def handle_action(self, action: Action) -> ActionResult:
        if action.type is ActionType.CONVERSE:
            validation_errors = validate_action(action)
            if validation_errors:
                return ActionResult.failure(errors=validation_errors)
            return ActionResult.success(
                events=[
                    {
                        "type": EventType.CONVERSE.value,
                        "actor_instance_id": action.actor_instance_id,
                        "message": str(action.parameters.get("message", "")),
                        "raw_input": action.raw_input,
                        "metadata": dict(action.metadata),
                    }
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
            return result

        if self.state is not before_state and "state" not in result.state_changes:
            merged_changes = dict(result.state_changes)
            merged_changes["state"] = {
                "from": before_state.value,
                "to": self.state.value,
            }
            return ActionResult.success(events=result.events, state_changes=merged_changes)

        return result

    def start_encounter(self, encounter: Encounter) -> ActionResult:
        before_state = self.state
        if self.state is not GameState.EXPLORATION:
            return ActionResult.failure(errors=["Encounter can only start while in exploration state."])

        result = self.encounter.start_encounter(self, encounter)
        if result.errors:
            return result
        if self.state is before_state:
            return ActionResult.success()
        return ActionResult.success(
            state_changes={
                "state": {
                    "from": before_state.value,
                    "to": self.state.value,
                }
            }
        )

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
            return ActionResult.success()
        return ActionResult.success(
            state_changes={
                "state": {
                    "from": before_state.value,
                    "to": self.state.value,
                }
            }
        )

    # serialize and deserialize functions 