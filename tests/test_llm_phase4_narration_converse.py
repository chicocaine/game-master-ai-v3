from dataclasses import dataclass
from types import SimpleNamespace

from core.enums import ActionType
from game.engine.interfaces import EngineContext
from game.enums import GameState
from game.llm.converse import ConverseResponder
from game.llm.config import load_llm_settings
from game.llm.contracts import LlmResponse
from game.llm.narrator.llm_narrator import LlmNarrator
from game.llm.providers.player_intent_provider import PlayerIntentLlmProvider


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


@dataclass
class _SessionStub:
    state: GameState
    party: list
    points: int = 0
    dungeon: object | None = None
    exploration: object | None = None
    encounter: object | None = None


def _settings():
    return load_llm_settings(
        env={
            "LLM_PROVIDER": "mock",
            "LLM_MODEL": "gpt-4.1-mini",
            "LLM_TIMEOUT_SECONDS": "30",
            "LLM_API_KEY": "test",
            "LLM_TEMPERATURE_ACTION": "0.2",
            "LLM_MAX_TOKENS_ACTION": "128",
            "LLM_TEMPERATURE_NARRATION": "0.7",
            "LLM_MAX_TOKENS_NARRATION": "128",
            "LLM_TEMPERATURE_CONVERSATION": "0.5",
            "LLM_MAX_TOKENS_CONVERSATION": "128",
        }
    )


def _session(state: GameState) -> _SessionStub:
    return _SessionStub(
        state=state,
        party=[SimpleNamespace(player_instance_id="player_1", hp=10, max_hp=10)],
        exploration=SimpleNamespace(current_room=SimpleNamespace(id="room_1", is_cleared=False)),
        encounter=SimpleNamespace(turn_order=["player_1", "enemy_1"], current_turn_index=0),
    )


def test_llm_narrator_only_triggers_for_triggerable_events():
    client = _FakeClient([LlmResponse(text='{"text":"narrated"}')])
    narrator = LlmNarrator(client=client, settings=_settings())

    non_trigger_events = [{"type": "action_validated"}]
    trigger_events = [{"type": "room_entered", "room_id": "room_2"}]

    assert narrator.narrate(non_trigger_events, _session(GameState.EXPLORATION), EngineContext(session_id="n1")) is None
    assert client.calls == 0

    output = narrator.narrate(trigger_events, _session(GameState.EXPLORATION), EngineContext(session_id="n1"))
    assert output == "narrated"
    assert client.calls == 1


def test_llm_narrator_uses_converse_responder_on_converse_event():
    narration_client = _FakeClient([])
    converse_client = _FakeClient([LlmResponse(text='{"reply":"Stay alert, hero.","tone":"calm"}')])
    responder = ConverseResponder(client=converse_client, settings=_settings())
    narrator = LlmNarrator(client=narration_client, settings=_settings(), converse_responder=responder)

    events = [{"type": "converse", "message": "Any tips?"}]

    output = narrator.narrate(events, _session(GameState.EXPLORATION), EngineContext(session_id="n2"))

    assert output == "Stay alert, hero."
    assert converse_client.calls == 1
    assert narration_client.calls == 0


def test_llm_narrator_handles_malformed_output_without_raising():
    client = _FakeClient([LlmResponse(text="not json")])
    narrator = LlmNarrator(client=client, settings=_settings())

    output = narrator.narrate(
        [{"type": "room_entered", "room_id": "room_2"}],
        _session(GameState.EXPLORATION),
        EngineContext(session_id="n3"),
    )

    assert output is None
    assert client.calls == 1


def test_player_intent_provider_routes_converse_and_keeps_stable_response_shape():
    intent_client = _FakeClient([LlmResponse(text='{"type":"converse","parameters":{"message":"hello"}}')])
    converse_client = _FakeClient([LlmResponse(text='{"reply":"Welcome back.","tone":"friendly","metadata":{"style":"gm"}}')])

    responder = ConverseResponder(client=converse_client, settings=_settings())
    provider = PlayerIntentLlmProvider(client=intent_client, settings=_settings(), converse_responder=responder)
    provider.enqueue(text="hello", actor_instance_id="player_1")

    action = provider.next_action(_session(GameState.EXPLORATION), EngineContext(session_id="p4"))

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.metadata["provider"] == "player_intent_llm"
    assert set(action.metadata["converse_response"].keys()) == {"reply", "tone", "metadata"}
    assert action.metadata["converse_response"]["reply"] == "Welcome back."


def test_player_intent_provider_keeps_converse_action_when_responder_fails():
    intent_client = _FakeClient([LlmResponse(text='{"type":"converse","parameters":{"message":"hello"}}')])
    converse_client = _FakeClient([LlmResponse(text="invalid")])

    responder = ConverseResponder(client=converse_client, settings=_settings())
    provider = PlayerIntentLlmProvider(client=intent_client, settings=_settings(), converse_responder=responder)
    provider.enqueue(text="hello", actor_instance_id="player_1")

    action = provider.next_action(_session(GameState.EXPLORATION), EngineContext(session_id="p5"))

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert "converse_response" not in action.metadata
