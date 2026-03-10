from dataclasses import dataclass

from core.enums import ActionType
from game.enums import GameState
from game.llm.config import load_llm_settings
from game.llm.contracts import LlmResponse
from game.llm.prompts.base import allowed_action_values_for_state
from game.llm.providers.player_intent_provider import PlayerIntentLlmProvider


class _FakeClient:
    def __init__(self, responses: list[LlmResponse]):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, request):
        self.calls += 1
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
    assert action.parameters["message"] == "What now?"
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
