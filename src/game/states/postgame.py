from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

from core.action import Action, validate_action
from core.action_result import ActionResult
from core.enums import ActionType, EventType
from game.enums import GameResult

if TYPE_CHECKING:
    from game.states.game_session import GameSession


@dataclass
class PostGameState:
    outcome: GameResult | None = None
    summary: Dict[str, Any] = field(default_factory=dict)
    SUPPORTED_ACTIONS = {
        ActionType.FINISH,
    }

    @staticmethod
    def _unsupported_action(action: Action) -> ActionResult:
        return ActionResult.failure(errors=[f"Unsupported postgame action type: '{action.type.value}'."])

    def handle_finish(self, session: "GameSession", action: Action | None = None) -> ActionResult:
        if self.outcome is None:
            outcome_value = action.parameters.get("outcome") if action is not None else None
            try:
                self.outcome = GameResult(str(outcome_value)) if outcome_value else GameResult.ABANDONED
            except ValueError:
                return ActionResult.failure(errors=["Invalid postgame outcome value."])

        self.summary = {
            "outcome": self.outcome.value,
            "points": int(getattr(session, "points", 0)),
            "party_size": len(getattr(session, "party", [])),
            "alive_players": len([player for player in getattr(session, "party", []) if getattr(player, "hp", 0) > 0]),
        }

        return ActionResult.success(
            events=[
                {
                    "type": EventType.GAME_FINISHED.value,
                    "outcome": self.outcome.value,
                    "summary": dict(self.summary),
                }
            ],
            state_changes={
                "postgame": {
                    "outcome": self.outcome.value,
                    "summary": dict(self.summary),
                }
            },
        )

    def handle_action(self, session: "GameSession", action: Action) -> ActionResult:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        validation_errors = validate_action(action)
        if validation_errors:
            return ActionResult.failure(errors=validation_errors)

        if action.type is ActionType.FINISH:
            return self.handle_finish(session, action)

        return self._unsupported_action(action)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value if self.outcome else "",
            "summary": dict(self.summary),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PostGameState":
        summary = data.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        outcome_value = str(data.get("outcome", ""))
        outcome = None
        if outcome_value:
            try:
                outcome = GameResult(outcome_value)
            except ValueError:
                outcome = None
        return cls(outcome=outcome, summary=summary)