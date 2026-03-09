from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, TYPE_CHECKING

from core.action import Action
from game.engine.interfaces import ActionProvider, EngineContext

if TYPE_CHECKING:
    from game.states.game_session import GameSession


@dataclass
class QueueActionProvider(ActionProvider):
    queue: Deque[Action] = field(default_factory=deque)

    def __init__(self, actions: list[Action] | None = None):
        self.queue = deque(actions or [])

    def next_action(self, session: "GameSession", ctx: EngineContext) -> Optional[Action]:
        if not self.queue:
            return None
        return self.queue.popleft()

    def enqueue(self, action: Action) -> None:
        self.queue.append(action)

    def pending_count(self) -> int:
        return len(self.queue)
