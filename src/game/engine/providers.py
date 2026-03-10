from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, TYPE_CHECKING

from core.action import Action, create_action
from core.enums import ActionType
from game.engine.interfaces import ActionProvider, EngineContext
from game.enums import GameState

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


@dataclass
class TurnAwareEnemyStubProvider(ActionProvider):
    """Deterministic enemy provider used for engine-loop testing and bootstrapping.

    The provider emits a single `END_TURN` action only when the active turn actor
    is an enemy instance id (`enemy_n`) during encounter state.
    """

    include_provider_metadata: bool = True

    @staticmethod
    def _current_turn_actor_instance_id(session: "GameSession") -> str:
        if getattr(session, "state", None) is not GameState.ENCOUNTER:
            return ""

        encounter_state = getattr(session, "encounter", None)
        if encounter_state is None:
            return ""

        turn_order = getattr(encounter_state, "turn_order", [])
        if not isinstance(turn_order, list) or not turn_order:
            return ""

        turn_index = getattr(encounter_state, "current_turn_index", -1)
        if not isinstance(turn_index, int) or turn_index < 0 or turn_index >= len(turn_order):
            return ""

        actor_id = turn_order[turn_index]
        return str(actor_id) if actor_id is not None else ""

    def next_action(self, session: "GameSession", ctx: EngineContext) -> Optional[Action]:
        actor_instance_id = self._current_turn_actor_instance_id(session)
        if not actor_instance_id.startswith("enemy_"):
            return None

        metadata = {"provider": "turn_aware_enemy_stub"} if self.include_provider_metadata else {}
        return create_action(
            action_type=ActionType.END_TURN,
            parameters={},
            actor_instance_id=actor_instance_id,
            metadata=metadata,
        )
