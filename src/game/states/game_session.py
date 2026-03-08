from dataclasses import dataclass, field
from typing import List

from core.action import Action
from core.enums import ActionType

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

    def handle_action(self, action: Action) -> List[str]:
        if self.state is GameState.PREGAME:
            return self.pregame.handle_action(self, action)

        if self.state is GameState.EXPLORATION:
            if action.type in {ActionType.MOVE, ActionType.REST}:
                return self.exploration.handle_action(self, action)
            if action.type in {ActionType.ATTACK, ActionType.CAST_SPELL, ActionType.END_TURN}:
                if self.encounter.current_encounter is None:
                    return ["Cannot process encounter action outside an active encounter."]
                return self.encounter.handle_action(self, action)
            return [f"Unsupported exploration action type: '{action.type.value}'."]

        if self.state is GameState.ENCOUNTER:
            if action.type in {ActionType.ATTACK, ActionType.CAST_SPELL, ActionType.END_TURN}:
                return self.encounter.handle_action(self, action)
            return [f"Unsupported encounter action type: '{action.type.value}'."]

        if self.state is GameState.POSTGAME:
            return ["Postgame action handling is not implemented yet."]

        return [f"Unsupported game state '{self.state.value}'."]

    def start_encounter(self, encounter: Encounter) -> List[str]:
        if self.state is not GameState.EXPLORATION:
            return ["Encounter can only start while in exploration state."]
        return self.encounter.start_encounter(self, encounter)

    def end_encounter(self) -> List[str]:
        if self.state is not GameState.ENCOUNTER:
            return ["Encounter can only end while in encounter state."]
        return self.encounter.end_encounter(self)

    # serialize and deserialize functions 