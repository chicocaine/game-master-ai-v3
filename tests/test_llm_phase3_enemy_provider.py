from dataclasses import dataclass
from types import SimpleNamespace

from game.core.enums import ActionType
from game.engine.interfaces import EngineContext
from game.enums import GameState
from game.llm.config import load_llm_settings
from game.llm.contracts import LlmResponse
from game.llm.providers.enemy_llm_provider import EnemyLlmActionProvider


class _FakeClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0
        self.last_request = None

    def complete(self, request):
        self.calls += 1
        self.last_request = request
        if not self._outcomes:
            raise RuntimeError("no outcomes configured")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _settings():
    return load_llm_settings(
        env={
            "LLM_PROVIDER": "mock",
            "LLM_MODEL": "gpt-4.1-mini",
            "LLM_TIMEOUT_SECONDS": "30",
            "LLM_API_KEY": "test",
            "LLM_TEMPERATURE_ENEMY": "0.2",
            "LLM_MAX_TOKENS_ENEMY": "256",
        }
    )


def _enemy(enemy_instance_id: str, persona: str = ""):
    return SimpleNamespace(enemy_instance_id=enemy_instance_id, hp=9, max_hp=12, persona=persona)


def _player(player_instance_id: str):
    return SimpleNamespace(player_instance_id=player_instance_id, hp=10, max_hp=10)


def _session(state: GameState, turn_order: list[str], turn_index: int, enemies: list, party: list):
    encounter = SimpleNamespace(
        turn_order=turn_order,
        current_turn_index=turn_index,
        current_encounter=SimpleNamespace(enemies=enemies),
    )
    return SimpleNamespace(
        state=state,
        encounter=encounter,
        party=party,
    )


def test_enemy_provider_only_emits_on_enemy_turn():
    client = _FakeClient([LlmResponse(text='{"type":"end_turn","parameters":{}}')])
    provider = EnemyLlmActionProvider(client=client, settings=_settings())

    non_encounter = _session(GameState.EXPLORATION, ["enemy_1"], 0, [_enemy("enemy_1")], [_player("player_1")])
    assert provider.next_action(non_encounter, EngineContext(session_id="s1")) is None

    player_turn = _session(
        GameState.ENCOUNTER,
        ["player_1", "enemy_1"],
        0,
        [_enemy("enemy_1")],
        [_player("player_1")],
    )
    assert provider.next_action(player_turn, EngineContext(session_id="s1")) is None
    assert client.calls == 0


def test_enemy_provider_fallbacks_to_end_turn_on_llm_error():
    client = _FakeClient([TimeoutError("boom")])
    provider = EnemyLlmActionProvider(client=client, settings=_settings())
    session = _session(
        GameState.ENCOUNTER,
        ["enemy_1", "player_1"],
        0,
        [_enemy("enemy_1")],
        [_player("player_1")],
    )

    action = provider.next_action(session, EngineContext(session_id="s2"))

    assert action is not None
    assert action.type is ActionType.END_TURN
    assert action.actor_instance_id == "enemy_1"
    assert action.metadata["fallback"] is True
    assert action.metadata["fallback_reason"].startswith("llm_error:")


def test_enemy_provider_validates_target_payload_and_fallbacks():
    client = _FakeClient(
        [
            LlmResponse(
                text='{"type":"attack","actor_instance_id":"enemy_1","parameters":{"attack_id":"claw","target_instance_ids":[]}}'
            )
        ]
    )
    provider = EnemyLlmActionProvider(client=client, settings=_settings())
    session = _session(
        GameState.ENCOUNTER,
        ["enemy_1", "player_1"],
        0,
        [_enemy("enemy_1")],
        [_player("player_1")],
    )

    action = provider.next_action(session, EngineContext(session_id="s3"))

    assert action.type is ActionType.END_TURN
    assert action.metadata["fallback_reason"] == "invalid_target_payload"


def test_enemy_provider_injects_persona_into_request_payload():
    client = _FakeClient(
        [
            LlmResponse(
                text='{"type":"end_turn","actor_instance_id":"enemy_1","parameters":{}}'
            )
        ]
    )
    provider = EnemyLlmActionProvider(client=client, settings=_settings())
    session = _session(
        GameState.ENCOUNTER,
        ["enemy_1", "player_1"],
        0,
        [_enemy("enemy_1", persona="cunning_assassin")],
        [_player("player_1")],
    )

    action = provider.next_action(session, EngineContext(session_id="s4"))

    assert action.type is ActionType.END_TURN
    user_message_content = client.last_request.messages[2].content
    assert "cunning_assassin" in user_message_content


def test_enemy_provider_accepts_valid_attack_payload():
    client = _FakeClient(
        [
            LlmResponse(
                text='{"type":"attack","actor_instance_id":"enemy_1","parameters":{"attack_id":"claw","target_instance_ids":["player_1"]}}'
            )
        ]
    )
    provider = EnemyLlmActionProvider(client=client, settings=_settings())
    session = _session(
        GameState.ENCOUNTER,
        ["enemy_1", "player_1"],
        0,
        [_enemy("enemy_1")],
        [_player("player_1")],
    )

    action = provider.next_action(session, EngineContext(session_id="s5"))

    assert action.type is ActionType.ATTACK
    assert action.actor_instance_id == "enemy_1"
    assert action.parameters["target_instance_ids"] == ["player_1"]
