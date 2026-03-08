from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

from core.action import Action, validate_action
from core.action_result import ActionResult
from core.enums import ActionType
from game.dungeons.dungeon import Encounter
from game.enums import GameState

if TYPE_CHECKING:
    from game.states.game_session import GameSession

@dataclass
class EncounterState:
    current_encounter: Encounter | None = None
    turn_order: List[str] = field(default_factory=list)  # actor instance ids
    current_turn_index: int = 0
    post_encounter_summary: Dict[str, Any] = field(default_factory=dict)
    SUPPORTED_ACTIONS = {
        ActionType.ATTACK,
        ActionType.CAST_SPELL,
        ActionType.END_TURN,
    }

    @staticmethod
    def _ok() -> List[str]:
        return []

    @staticmethod
    def _unsupported_action_result(action: Action) -> ActionResult:
        return ActionResult.failure(errors=[f"Unsupported encounter action type: '{action.type.value}'."])

    @staticmethod
    def _transition_result(session: "GameSession", target_state: GameState) -> ActionResult:
        if hasattr(session, "transition_to"):
            transition_result = session.transition_to(target_state)
            if isinstance(transition_result, ActionResult):
                return transition_result
            return ActionResult.from_errors(transition_result)
        session.state = target_state
        return ActionResult.success(
            state_changes={"state": {"to": target_state.value}}
        )

    def _current_actor_instance_id(self) -> str:
        if not self.turn_order:
            return ""
        if self.current_turn_index < 0 or self.current_turn_index >= len(self.turn_order):
            return ""
        return self.turn_order[self.current_turn_index]

    def _validate_action_turn_owner(self, action: Action) -> List[str]:
        errors = validate_action(action)
        if errors:
            return errors
        current_actor = self._current_actor_instance_id()
        if not current_actor:
            return ["Current turn actor is not available."]
        if action.actor_instance_id != current_actor:
            return [
                f"Action actor '{action.actor_instance_id}' is invalid for current turn; expected '{current_actor}'."
            ]
        return self._ok()

    # properties of encounter

    def start_encounter(self, session: "GameSession", encounter: Encounter) -> ActionResult:
        if encounter is None:
            return ActionResult.failure(errors=["Encounter cannot be None."])

        self.current_encounter = encounter
        player_ids = [player.player_instance_id for player in session.party if player.player_instance_id and player.hp > 0]
        enemy_ids = [enemy.enemy_instance_id for enemy in encounter.enemies if enemy.enemy_instance_id and enemy.hp > 0]
        self.turn_order = [*player_ids, *enemy_ids]
        self.current_turn_index = 0
        return self._transition_result(session, GameState.ENCOUNTER)

    def handle_attack(self, session: "GameSession", action: Action) -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to handle attack."])
        if action.type is not ActionType.ATTACK:
            return ActionResult.failure(errors=["Invalid action type for attack handler."])
        action_errors = self._validate_action_turn_owner(action)
        if action_errors:
            return ActionResult.failure(errors=action_errors)
        return ActionResult.failure(errors=["Attack resolution is not implemented yet."])

    def handle_cast_spell(self, session: "GameSession", action: Action) -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to handle spell cast."])
        if action.type is not ActionType.CAST_SPELL:
            return ActionResult.failure(errors=["Invalid action type for cast spell handler."])
        action_errors = self._validate_action_turn_owner(action)
        if action_errors:
            return ActionResult.failure(errors=action_errors)
        return ActionResult.failure(errors=["Spell resolution is not implemented yet."])

    def handle_end_turn(self, session: "GameSession", action: Action | None = None) -> ActionResult:
        if action is not None:
            if action.type is not ActionType.END_TURN:
                return ActionResult.failure(errors=["Invalid action type for end turn handler."])
            action_errors = self._validate_action_turn_owner(action)
            if action_errors:
                return ActionResult.failure(errors=action_errors)
        return self.advance_turn(session)

    def handle_action(self, session: "GameSession", action: Action) -> ActionResult:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action_result(action)

        if action.type is ActionType.ATTACK:
            return self.handle_attack(session, action)
        if action.type is ActionType.CAST_SPELL:
            return self.handle_cast_spell(session, action)
        if action.type is ActionType.END_TURN:
            return self.handle_end_turn(session, action)
        return self._unsupported_action_result(action)

    def advance_turn(self, session: "GameSession") -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to advance turn."])
        if not self.turn_order:
            return ActionResult.failure(errors=["Cannot advance turn because turn order is empty."])

        # check if next actor in turn order is stunned or downed(hp=0), if so, skip turn
        # advance turn
        # validate current actor turn
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        return ActionResult.success()

    def end_encounter(self, session: "GameSession") -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to end."])

        self.current_encounter.cleared = True
        self.post_encounter_summary = {
            "encounter_id": self.current_encounter.id,
            "status": "placeholder_cleared",
        }
        self.current_encounter = None
        self.turn_order = []
        self.current_turn_index = 0
        return self._transition_result(session, GameState.EXPLORATION)

    def to_dict(self) -> dict:
        return {
            "current_encounter_id": self.current_encounter.id if self.current_encounter else "",
            "turn_order": list(self.turn_order),
            "current_turn_index": self.current_turn_index,
            "post_encounter_summary": dict(self.post_encounter_summary),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterState":
        turn_order = data.get("turn_order", [])
        if not isinstance(turn_order, list):
            turn_order = []
        summary = data.get("post_encounter_summary", {})
        if not isinstance(summary, dict):
            summary = {}
        return cls(
            current_encounter=None,
            turn_order=[str(item) for item in turn_order],
            current_turn_index=int(data.get("current_turn_index", 0)),
            post_encounter_summary=summary,
        )


    # serialize and deserialize functions