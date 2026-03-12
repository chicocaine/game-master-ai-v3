import json
from dataclasses import dataclass
from types import SimpleNamespace

from game.core.enums import ActionType
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


def test_llm_narrator_does_not_trigger_on_converse_event():
    narration_client = _FakeClient([])
    narrator = LlmNarrator(client=narration_client, settings=_settings())

    events = [{"type": "converse", "message": "Any tips?"}]

    output = narrator.narrate(events, _session(GameState.EXPLORATION), EngineContext(session_id="n2"))

    assert output is None
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


def test_player_intent_provider_returns_intent_only_converse_action():
    intent_client = _FakeClient([LlmResponse(text='{"type":"converse","parameters":{"message":"hello"}}')])
    provider = PlayerIntentLlmProvider(client=intent_client, settings=_settings())
    provider.enqueue(text="hello", actor_instance_id="player_1")

    action = provider.next_action(_session(GameState.EXPLORATION), EngineContext(session_id="p4"))

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.metadata["provider"] == "player_intent_llm"
    assert "converse_response" not in action.metadata


def test_player_intent_provider_keeps_converse_action_without_responder_coupling():
    intent_client = _FakeClient([LlmResponse(text='{"type":"converse","parameters":{"message":"hello"}}')])
    provider = PlayerIntentLlmProvider(client=intent_client, settings=_settings())
    provider.enqueue(text="hello", actor_instance_id="player_1")

    action = provider.next_action(_session(GameState.EXPLORATION), EngineContext(session_id="p5"))

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert "converse_response" not in action.metadata


def test_converse_responder_adds_response_class_metadata_when_missing():
    converse_client = _FakeClient([LlmResponse(text='{"reply":"You can move to room_2.","tone":"helpful"}')])
    responder = ConverseResponder(client=converse_client, settings=_settings())

    payload = responder.generate("Where can I go?", {"state": "exploration"})

    assert payload is not None
    assert payload["metadata"]["response_class"] in {
        "clarification",
        "world_query",
        "light_roleplay",
        "blocked_transition",
    }


def test_llm_narrator_includes_beats_and_sentence_policy_in_request_payload():
    client = _FakeClient([LlmResponse(text='{"text":"One. Two."}')])
    narrator = LlmNarrator(client=client, settings=_settings())

    events = [
        {"type": "room_entered", "room_id": "room_2"},
        {"type": "attack_hit", "attacker": "player_1", "target": "enemy_1"},
        {"type": "damage_applied", "target": "enemy_1", "amount": 3},
    ]

    output = narrator.narrate(events, _session(GameState.EXPLORATION), EngineContext(session_id="n6"))

    assert output == "One. Two."
    user_payload = None
    for message in client.last_request.messages:
        if message.role == "user":
            user_payload = json.loads(message.content)
            break
    assert user_payload is not None
    assert isinstance(user_payload.get("beats"), list)
    assert user_payload["narrative_policy"]["max_sentences"] == 5
    assert 1 <= user_payload["narrative_policy"]["target_sentences"] <= 5


def test_llm_narrator_enforces_five_sentence_hard_limit():
    long_text = "S1. S2. S3. S4. S5. S6."
    client = _FakeClient([LlmResponse(text='{"text":"' + long_text + '"}')])
    narrator = LlmNarrator(client=client, settings=_settings())

    output = narrator.narrate(
        [{"type": "room_entered", "room_id": "room_2"}],
        _session(GameState.EXPLORATION),
        EngineContext(session_id="n7"),
    )

    assert output is not None
    assert "S6." not in output
