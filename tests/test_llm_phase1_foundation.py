import pytest

from game.llm.client import RetryPolicy, invoke_with_retry
from game.llm.config import load_llm_settings
from game.llm.contracts import LlmMessage, LlmRequest, LlmResponse
from game.llm.errors import (
    LlmConfigurationError,
    LlmResponseParseError,
    LlmRetryExhaustedError,
    LlmSchemaValidationError,
    LlmTimeoutError,
)
from game.llm.json_parse import (
    parse_json_object,
    validate_action_payload,
    validate_context_envelope,
    validate_narration_payload,
)


class _FakeClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def complete(self, request: LlmRequest) -> LlmResponse:
        self.calls += 1
        if not self._outcomes:
            raise RuntimeError("no outcomes configured")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _request() -> LlmRequest:
    return LlmRequest(
        model="gpt-4.1-mini",
        messages=[LlmMessage(role="user", content="hello")],
        temperature=0.2,
        max_tokens=128,
        timeout_seconds=10,
    )


def test_load_llm_settings_reads_defaults_and_domain_overrides():
    env = {
        "LLM_API_KEY": "k1",
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "model-x",
        "LLM_TIMEOUT_SECONDS": "45",
        "LLM_TEMPERATURE": "0.4",
        "LLM_MAX_TOKENS": "2000",
        "LLM_TEMPERATURE_ACTION": "0.1",
        "LLM_MAX_TOKENS_ACTION": "111",
    }

    settings = load_llm_settings(env=env)

    assert settings.api_key == "k1"
    assert settings.provider == "openai"
    assert settings.model == "model-x"
    assert settings.timeout_seconds == 45

    assert settings.action.temperature == 0.1
    assert settings.action.max_tokens == 111

    # Domains without explicit overrides inherit global values.
    assert settings.enemy.temperature == 0.4
    assert settings.enemy.max_tokens == 2000
    assert settings.narration.temperature == 0.4
    assert settings.conversation.max_tokens == 2000


def test_load_llm_settings_allows_missing_api_key_when_not_required():
    settings = load_llm_settings(env={"LLM_PROVIDER": "mock"}, require_api_key=False)
    assert settings.api_key == ""
    assert settings.provider == "mock"


def test_load_llm_settings_rejects_invalid_values():
    with pytest.raises(LlmConfigurationError):
        load_llm_settings(env={"LLM_PROVIDER": "unknown", "LLM_API_KEY": "x"})

    with pytest.raises(LlmConfigurationError):
        load_llm_settings(env={"LLM_API_KEY": "x", "LLM_TEMPERATURE": "3.0"})

    with pytest.raises(LlmConfigurationError):
        load_llm_settings(env={"LLM_API_KEY": "x", "LLM_MAX_TOKENS": "0"})


def test_parse_json_object_handles_code_fence():
    raw = """
    Here is your payload:
    ```json
    {"type": "move", "parameters": {"destination_room_id": "room_2"}}
    ```
    """

    payload = parse_json_object(raw)

    assert payload["type"] == "move"
    assert payload["parameters"]["destination_room_id"] == "room_2"


def test_parse_json_object_raises_for_invalid_json():
    with pytest.raises(LlmResponseParseError):
        parse_json_object("not json")


def test_validate_action_payload_requires_non_empty_type_and_object_parameters():
    payload = validate_action_payload({"type": "converse", "parameters": {"message": "hello"}})
    assert payload["type"] == "converse"
    assert payload["parameters"]["message"] == "hello"

    with pytest.raises(LlmSchemaValidationError):
        validate_action_payload({"type": "", "parameters": {}})

    with pytest.raises(LlmSchemaValidationError):
        validate_action_payload({"type": "move", "parameters": "bad"})


def test_validate_narration_payload_accepts_minimum_shape():
    payload = validate_narration_payload({"text": "A torch flickers."})
    assert payload["text"] == "A torch flickers."
    assert payload["focus_event_ids"] == []

    with pytest.raises(LlmSchemaValidationError):
        validate_narration_payload({"text": "ok", "focus_event_ids": ["", "event_2"]})


def test_invoke_with_retry_recovers_after_timeout():
    client = _FakeClient(
        [
            TimeoutError("first timeout"),
            LlmResponse(text='{"type":"end_turn","parameters":{}}'),
        ]
    )

    response = invoke_with_retry(
        client=client,
        request=_request(),
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
        sleep_fn=lambda _: None,
    )

    assert client.calls == 2
    assert response.text


def test_invoke_with_retry_raises_exhausted_with_timeout_last_error():
    client = _FakeClient([TimeoutError("t1"), TimeoutError("t2")])

    with pytest.raises(LlmRetryExhaustedError) as exc:
        invoke_with_retry(
            client=client,
            request=_request(),
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
            sleep_fn=lambda _: None,
        )

    assert exc.value.attempts == 2
    assert isinstance(exc.value.last_error, LlmTimeoutError)


def test_invoke_with_retry_does_not_retry_non_retriable_errors():
    client = _FakeClient([LlmResponseParseError("bad json")])

    with pytest.raises(LlmResponseParseError):
        invoke_with_retry(
            client=client,
            request=_request(),
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
            sleep_fn=lambda _: None,
        )

    assert client.calls == 1


def test_validate_context_envelope_accepts_minimum_valid_shape():
    payload = validate_context_envelope(
        {
            "identity": {"name": "game-master-ai", "aliases": ["dm", "game master"]},
            "past_context": {"timeline": [{"player_input": "move to room 2"}]},
            "current_context": {"state": "exploration", "current_room_id": "room_1"},
            "allowed_actions": ["move", "rest", "converse"],
            "actor_context": {"actor_instance_id": "player_1"},
        }
    )

    assert payload["identity"]["name"] == "game-master-ai"
    assert payload["allowed_actions"] == ["move", "rest", "converse"]
    assert payload["past_context"]["timeline"][0]["player_input"] == "move to room 2"


def test_validate_context_envelope_rejects_missing_required_sections():
    with pytest.raises(LlmSchemaValidationError):
        validate_context_envelope(
            {
                "identity": {"name": "game-master-ai", "aliases": []},
                "current_context": {},
                "allowed_actions": ["converse"],
                "actor_context": {},
            }
        )


def test_validate_context_envelope_rejects_type_mismatches():
    with pytest.raises(LlmSchemaValidationError):
        validate_context_envelope(
            {
                "identity": {"name": "game-master-ai", "aliases": "dm"},
                "past_context": {"timeline": []},
                "current_context": {},
                "allowed_actions": ["converse"],
                "actor_context": {},
            }
        )

    with pytest.raises(LlmSchemaValidationError):
        validate_context_envelope(
            {
                "identity": {"name": "game-master-ai", "aliases": ["dm"]},
                "past_context": {"timeline": "bad"},
                "current_context": {},
                "allowed_actions": ["converse"],
                "actor_context": {},
            }
        )
