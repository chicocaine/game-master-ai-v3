from dataclasses import dataclass
import json

import pytest

from game.core.enums import ActionType
from game.engine.interfaces import EngineContext
from game.enums import GameState
from game.llm.config import load_llm_settings
from game.llm.contracts import LlmResponse
from game.llm.prompts.base import allowed_action_values_for_state
from game.llm.providers.player_intent_provider import PlayerIntentLlmProvider


class _FakeClient:
    def __init__(self, responses: list[LlmResponse]):
        self.responses = list(responses)
        self.calls = 0
        self.last_request = None

    def complete(self, request):
        self.calls += 1
        self.last_request = request
        if not self.responses:
            raise RuntimeError("no response configured")
        return self.responses.pop(0)


@dataclass
class _SessionStub:
    state: GameState
    party: list = None
    points: int = 0
    dungeon: object | None = None
    exploration: object | None = None
    encounter: object | None = None

    def __post_init__(self):
        if self.party is None:
            self.party = []


def _settings():
    return load_llm_settings(
        env={
            "LLM_PROVIDER": "mock",
            "LLM_MODEL": "gpt-4.1-mini",
            "LLM_TIMEOUT_SECONDS": "30",
            "LLM_API_KEY": "test",
            "LLM_TEMPERATURE_ACTION": "0.2",
            "LLM_MAX_TOKENS_ACTION": "512",
        }
    )


def test_prompt_allowed_actions_match_expected_by_state():
    assert allowed_action_values_for_state(GameState.PREGAME) == [
        "create_player",
        "remove_player",
        "edit_player",
        "choose_dungeon",
        "start",
        "converse",
    ]
    assert allowed_action_values_for_state(GameState.EXPLORATION) == ["move", "rest", "converse"]
    assert allowed_action_values_for_state(GameState.ENCOUNTER) == ["attack", "cast_spell", "end_turn", "converse"]
    assert allowed_action_values_for_state(GameState.POSTGAME) == ["finish", "converse"]


def test_provider_filters_disallowed_action_type_to_fallback_converse():
    client = _FakeClient(
        [
            LlmResponse(
                text='{"type":"attack","parameters":{"attack_id":"slash","target_instance_ids":["enemy_1"]}}'
            )
        ]
    )
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="attack now", actor_instance_id="player_1")

    action = provider.next_action(_SessionStub(state=GameState.PREGAME), ctx=None)

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.parameters["message"] == "attack now"
    assert action.metadata["fallback"] is True
    assert action.metadata["fallback_reason"] == "disallowed_action_type"


def test_provider_normalizes_query_alias_to_converse():
    client = _FakeClient([LlmResponse(text='{"type":"query","parameters":{"question":"What now?"}}')])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="what now", actor_instance_id="player_1")

    action = provider.next_action(_SessionStub(state=GameState.EXPLORATION), ctx=None)

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.parameters["message"] == "what now"
    assert action.actor_instance_id == "player_1"


def test_provider_fallbacks_on_malformed_json_output():
    client = _FakeClient([LlmResponse(text="not a json object")])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="hello gm", actor_instance_id="player_2")

    action = provider.next_action(_SessionStub(state=GameState.EXPLORATION), ctx=None)

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.parameters["message"] == "hello gm"
    assert action.metadata["fallback"] is True
    assert action.metadata["fallback_reason"].startswith("llm_error:")


def test_provider_returns_none_when_queue_is_empty():
    client = _FakeClient([])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())

    action = provider.next_action(_SessionStub(state=GameState.PREGAME), ctx=None)

    assert action is None
    assert client.calls == 0


def test_provider_routes_start_to_converse_when_pregame_requirements_missing():
    client = _FakeClient([LlmResponse(text='{"type":"start","parameters":{}}')])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="start now", actor_instance_id="player_1")

    action = provider.next_action(_SessionStub(state=GameState.PREGAME), ctx=None)

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.metadata["fallback"] is True
    assert action.metadata["fallback_reason"] == "blocked_start"
    assert action.parameters["message"] == "start now"
    assert "at least one player" in action.reasoning
    assert "dungeon selection" in action.reasoning


def test_provider_allows_start_when_pregame_requirements_are_met():
    client = _FakeClient([LlmResponse(text='{"type":"start","parameters":{}}')])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="start now", actor_instance_id="player_1")

    session = _SessionStub(state=GameState.PREGAME, party=[object()], dungeon=object())
    action = provider.next_action(session, ctx=None)

    assert action is not None
    assert action.type is ActionType.START


@pytest.mark.parametrize(
    ("response_text", "expected_action_type"),
    [
        (
            '{"type":"create_player","parameters":{"id":"player_elara","name":"Elara","description":"Mage","race":"race_human","archetype":"arch_mage","weapons":["wpn_sage_staff"]},"reasoning":"Create a player."}',
            "create_player",
        ),
        (
            '{"type":"edit_player","parameters":{"player_instance_id":"player_1","id":"player_elara","name":"Elara","description":"Mage","race":"race_human","archetype":"arch_mage","weapons":["wpn_sage_staff"]},"reasoning":"Edit the player."}',
            "edit_player",
        ),
        (
            '{"type":"remove_player","parameters":{"player_instance_id":"player_1"},"reasoning":"Remove the player."}',
            "remove_player",
        ),
    ],
)
def test_provider_allows_pregame_setup_actions_directly(response_text, expected_action_type):
    client = _FakeClient([LlmResponse(text=response_text)])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="handle setup", actor_instance_id="player_1")

    action = provider.next_action(_SessionStub(state=GameState.PREGAME), ctx=None)

    assert action is not None
    assert action.type.value == expected_action_type


def test_provider_allows_choose_dungeon_directly_in_pregame():
    client = _FakeClient(
        [
            LlmResponse(
                text='{"type":"choose_dungeon","parameters":{"dungeon":"dng_ember_ruins"},"reasoning":"Player explicitly selected a dungeon id."}'
            )
        ]
    )
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="I choose ember ruins", actor_instance_id="player_1")

    action = provider.next_action(_SessionStub(state=GameState.PREGAME), ctx=None)

    assert action is not None
    assert action.type is ActionType.CHOOSE_DUNGEON
    assert action.parameters["dungeon"] == "dng_ember_ruins"


def test_provider_routes_ambiguous_input_to_converse_without_model_call():
    client = _FakeClient([LlmResponse(text='{"type":"move","parameters":{"destination_room_id":"room_2"}}')])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="?", actor_instance_id="player_1")

    action = provider.next_action(_SessionStub(state=GameState.EXPLORATION), ctx=None)

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.metadata["fallback_reason"] == "ambiguous_input"
    assert action.parameters["message"] == "?"
    assert "ambiguous" in action.reasoning.lower() or "clarification" in action.reasoning.lower()
    assert client.calls == 0


def test_provider_debug_context_includes_llm_returned_action(monkeypatch, capsys):
    monkeypatch.setenv("LLM_DEBUG_CONTEXT", "1")
    monkeypatch.setenv("LLM_DEBUG_CONTEXT_DOMAINS", "player_intent")

    client = _FakeClient([LlmResponse(text='{"type":"move","parameters":{"destination_room_id":"room_2"}}')])
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())
    provider.enqueue(text="go to room 2", actor_instance_id="player_1")

    action = provider.next_action(_SessionStub(state=GameState.EXPLORATION), ctx=EngineContext(session_id="debug_ctx"))

    assert action is not None
    output = capsys.readouterr().out
    assert '"llm_returned_action"' in output
    assert '"type": "move"' in output


def test_provider_request_includes_recent_conversation_from_previous_turn():
    client = _FakeClient(
        [
            LlmResponse(text='{"type":"converse","parameters":{"message":"first"},"reasoning":"Need clarification."}'),
            LlmResponse(text='{"type":"converse","parameters":{"message":"second"},"reasoning":"Need clarification."}'),
        ]
    )
    provider = PlayerIntentLlmProvider(client=client, settings=_settings())

    provider.enqueue(text="I choose ember ruins", actor_instance_id="player_1")
    first_action = provider.next_action(_SessionStub(state=GameState.PREGAME), ctx=None)
    assert first_action is not None

    provider.enqueue(text="okay sure", actor_instance_id="player_1")
    second_action = provider.next_action(_SessionStub(state=GameState.PREGAME), ctx=None)
    assert second_action is not None

    user_payload = None
    for message in client.last_request.messages:
        if message.role == "user":
            user_payload = json.loads(message.content)
            break

    assert isinstance(user_payload, dict)
    assert isinstance(user_payload.get("recent_conversation"), list)
    assert any(
        entry.get("player_input") == "I choose ember ruins"
        for entry in user_payload["recent_conversation"]
        if isinstance(entry, dict)
    )
