from types import SimpleNamespace

from game.core.action import create_action
from game.core.enums import ActionType
from game.enums import GameResult
from game.states.postgame import PostGameState


class _StubSession:
    def __init__(self) -> None:
        self.points = 5
        self.party = [SimpleNamespace(hp=10), SimpleNamespace(hp=0)]

    def reset_for_new_run(self) -> dict:
        return {"state": {"to": "pregame"}}


def test_postgame_finish_coerces_outcome_and_summarizes() -> None:
    session = _StubSession()
    state = PostGameState()
    action = create_action(
        ActionType.FINISH,
        parameters={"outcome": GameResult.WIN.value},
        actor_instance_id="system",
    )

    result = state.handle_action(session, action)

    assert result.ok is True
    assert state.outcome is GameResult.WIN
    assert state.summary["alive_players"] == 1
    assert state.summary["points"] == 5
    assert result.events[0]["type"] == "game_finished"
    assert result.events[0]["outcome"] == "win"
