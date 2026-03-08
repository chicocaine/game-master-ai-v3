from dataclasses import dataclass, field
from typing import Dict, List, Set

from core.action import Action

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

    def transition_to(self, target_state: GameState) -> List[str]:
        if self.state is target_state:
            return []
        if not self.can_transition_to(target_state):
            return [
                f"Invalid state transition from '{self.state.value}' to '{target_state.value}'."
            ]
        self.state = target_state
        return []

    def handle_action(self, action: Action) -> List[str]:
        if self.state is GameState.PREGAME:
            return self.pregame.handle_action(self, action)

        if self.state is GameState.EXPLORATION:
            return self.exploration.handle_action(self, action)

        if self.state is GameState.ENCOUNTER:
            return self.encounter.handle_action(self, action)

        if self.state is GameState.POSTGAME:
            return self.postgame.handle_action(self, action)

        return [f"Unsupported game state '{self.state.value}'."]

    def start_encounter(self, encounter: Encounter) -> List[str]:
        if self.state is not GameState.EXPLORATION:
            return ["Encounter can only start while in exploration state."]
        return self.encounter.start_encounter(self, encounter)

    def start_room_encounter(self) -> List[str]:
        if self.state is not GameState.EXPLORATION:
            return ["Room encounter can only start while in exploration state."]
        if self.exploration.current_room is None:
            return ["Cannot start room encounter without a current room."]

        for room_encounter in self.exploration.current_room.encounters:
            if not room_encounter.cleared:
                return self.start_encounter(room_encounter)

        return ["No uncleared encounters in current room."]

    def end_encounter(self) -> List[str]:
        if self.state is not GameState.ENCOUNTER:
            return ["Encounter can only end while in encounter state."]
        errors = self.encounter.end_encounter(self)
        if errors:
            return errors

        current_room = self.exploration.current_room
        if current_room is not None and current_room.encounters:
            current_room.is_cleared = all(room_encounter.cleared for room_encounter in current_room.encounters)

        return []

    # serialize and deserialize functions 