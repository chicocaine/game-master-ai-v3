from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

from core.action import Action, validate_action
from core.action_result import ActionResult
from core.enums import ActionType
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
    def _unsupported_action(action: Action) -> list[str]:
        return [f"Unsupported postgame action type: '{action.type.value}'."]

    def handle_finish(self, session: "GameSession") -> list[str]:
        return ["Postgame finish handling is not implemented yet."]

    def handle_action(self, session: "GameSession", action: Action) -> list[str]:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        validation_errors = validate_action(action)
        if validation_errors:
            return validation_errors

        if action.type is ActionType.FINISH:
            return self.handle_finish(session)

        return self._unsupported_action(action)

    def handle_action_result(self, session: "GameSession", action: Action) -> ActionResult:
        errors = self.handle_action(session, action)
        if errors:
            return ActionResult.failure(errors=errors)
        return ActionResult.success()

    # serialize and deserialize functions