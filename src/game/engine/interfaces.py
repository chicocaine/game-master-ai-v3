from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

from game.core.action import Action
from game.core.action_result import ActionResult

if TYPE_CHECKING:
    from game.states.game_session import GameSession


@dataclass
class EngineContext:
    session_id: str
    step_count: int = 0
    seed: int = 0

    @property
    def turn_index(self) -> int:
        return self.step_count

    @turn_index.setter
    def turn_index(self, value: int) -> None:
        self.step_count = int(value)


class ActionProvider(Protocol):
    def next_action(self, session: "GameSession", ctx: EngineContext) -> Optional[Action]:
        """Return the next action candidate, or None when no action is available."""


class Narrator(Protocol):
    def narrate(
        self,
        events: List[Dict[str, Any]],
        session: "GameSession",
        ctx: EngineContext,
    ) -> Optional[str]:
        """Render optional narration text for an emitted event batch."""


class EventSink(Protocol):
    def publish(self, events: List[Dict[str, Any]], ctx: EngineContext) -> None:
        """Publish an event batch to one sink destination."""


class Persistence(Protocol):
    def load(self, session_id: str) -> Optional["GameSession"]:
        """Load an existing session snapshot when available."""

    def save_checkpoint(
        self,
        session: "GameSession",
        action: Action,
        result: ActionResult,
        ctx: EngineContext,
    ) -> None:
        """Persist state after one handled action."""
