from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

from game.enums import GameResult

if TYPE_CHECKING:
    from game.states.game_session import GameSession


@dataclass
class PostGameState:
    outcome: GameResult | None = None
    summary: Dict[str, Any] = field(default_factory=dict)

    def handle_finish(self, session: "GameSession") -> list[str]:
        return ["Postgame finish handling is not implemented yet."]

    # serialize and deserialize functions