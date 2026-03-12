from types import SimpleNamespace

from game.core.enums import ActionType
from game.engine.interfaces import EngineContext
from game.engine.providers import TurnAwareEnemyStubProvider
from game.enums import GameState


def _make_session(state: GameState, turn_order: list[str], turn_index: int):
    encounter = SimpleNamespace(turn_order=turn_order, current_turn_index=turn_index)
    return SimpleNamespace(state=state, encounter=encounter)


def test_turn_aware_enemy_stub_provider_returns_end_turn_for_enemy_turn():
    provider = TurnAwareEnemyStubProvider()
    ctx = EngineContext(session_id="provider_1")
    session = _make_session(GameState.ENCOUNTER, ["player_1", "enemy_1"], 1)

    action = provider.next_action(session, ctx)

    assert action is not None
    assert action.type is ActionType.END_TURN
    assert action.actor_instance_id == "enemy_1"
    assert action.metadata.get("provider") == "turn_aware_enemy_stub"


def test_turn_aware_enemy_stub_provider_returns_none_for_player_turn():
    provider = TurnAwareEnemyStubProvider()
    ctx = EngineContext(session_id="provider_2")
    session = _make_session(GameState.ENCOUNTER, ["player_1", "enemy_1"], 0)

    assert provider.next_action(session, ctx) is None


def test_turn_aware_enemy_stub_provider_returns_none_outside_encounter_state():
    provider = TurnAwareEnemyStubProvider()
    ctx = EngineContext(session_id="provider_3")
    session = _make_session(GameState.EXPLORATION, ["enemy_1"], 0)

    assert provider.next_action(session, ctx) is None


def test_turn_aware_enemy_stub_provider_handles_invalid_turn_index():
    provider = TurnAwareEnemyStubProvider()
    ctx = EngineContext(session_id="provider_4")
    session = _make_session(GameState.ENCOUNTER, ["enemy_1"], 3)

    assert provider.next_action(session, ctx) is None
