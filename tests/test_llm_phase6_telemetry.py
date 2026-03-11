import json
from dataclasses import dataclass
from types import SimpleNamespace

from game.core.enums import ActionType
from game.engine.interfaces import EngineContext
from game.enums import GameState
from game.llm.config import load_llm_settings
from game.llm.contracts import LlmMessage, LlmRequest, LlmResponse
from game.llm.converse import ConverseResponder
from game.llm.providers.player_intent_provider import PlayerIntentLlmProvider
from game.llm.telemetry import InMemoryLlmTelemetrySink, JsonlLlmTelemetrySink, LlmMetricsTracker, LlmTelemetry


class _FakeClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    def complete(self, request):
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


def test_player_provider_emits_call_and_validation_telemetry_with_prompt_version():
    sink = InMemoryLlmTelemetrySink()
    telemetry = LlmTelemetry(sinks=[sink])

    provider = PlayerIntentLlmProvider(
        client=_FakeClient([LlmResponse(text='{"type":"converse","parameters":{"message":"hello"}}')]),
        settings=_settings(),
        telemetry=telemetry,
    )
    provider.enqueue("hello", actor_instance_id="player_1")

    action = provider.next_action(_session(GameState.EXPLORATION), EngineContext(session_id="t1"))

    assert action is not None
    assert action.type is ActionType.CONVERSE

    call_events = [event for event in sink.events if event.get("kind") == "llm_call"]
    validation_events = [event for event in sink.events if event.get("kind") == "llm_validation"]

    assert len(call_events) == 1
    assert call_events[0]["domain"] == "player_intent"
    assert call_events[0]["prompt_version"] == "player_intent.v2"
    assert call_events[0]["success"] is True
    assert call_events[0]["context_token_estimate"] >= 0
    assert call_events[0]["beat_count"] == 0
    assert len(validation_events) == 1
    assert validation_events[0]["valid"] is True


def test_fallback_and_metrics_are_emitted_on_parse_failure():
    sink = InMemoryLlmTelemetrySink()
    metrics = LlmMetricsTracker()
    telemetry = LlmTelemetry(sinks=[sink, metrics])

    provider = PlayerIntentLlmProvider(
        client=_FakeClient([LlmResponse(text="not-json")]),
        settings=_settings(),
        telemetry=telemetry,
    )
    provider.enqueue("help", actor_instance_id="player_1")

    action = provider.next_action(_session(GameState.EXPLORATION), EngineContext(session_id="t2"))

    assert action is not None
    assert action.type is ActionType.CONVERSE
    assert action.metadata.get("fallback") is True

    fallback_events = [event for event in sink.events if event.get("kind") == "llm_fallback"]
    assert len(fallback_events) == 1
    assert fallback_events[0]["domain"] == "player_intent"

    bucket = metrics.counters["player_intent"]
    assert bucket["calls"] == 1
    assert bucket["call_failure"] == 1
    assert bucket["validation_failure"] == 1
    assert bucket["fallbacks"] == 1


def test_jsonl_telemetry_sink_redacts_secrets(tmp_path):
    sink = JsonlLlmTelemetrySink(base_dir=str(tmp_path / "events"), file_name="llm.jsonl")
    telemetry = LlmTelemetry(sinks=[sink])

    request = LlmRequest(
        model="gpt-4.1-mini",
        messages=[LlmMessage(role="user", content="hi")],
        temperature=0.2,
        max_tokens=32,
        timeout_seconds=10,
        metadata={
            "provider": "test",
            "prompt_version": "test.v1",
            "api_key": "super-secret-key",
            "nested": {"token": "sensitive-token"},
        },
    )

    telemetry.emit_call(
        domain="test",
        request=request,
        success=True,
        latency_ms=1.0,
        response_text='{"ok":true}',
    )

    output_file = tmp_path / "events" / "llm.jsonl"
    lines = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    raw = lines[0]
    assert "super-secret-key" not in raw
    assert "sensitive-token" not in raw

    record = json.loads(raw)
    assert record["request_metadata"]["api_key"] == "[REDACTED]"
    assert record["request_metadata"]["nested"]["token"] == "[REDACTED]"


def test_converse_responder_emits_prompt_version_telemetry():
    sink = InMemoryLlmTelemetrySink()
    telemetry = LlmTelemetry(sinks=[sink])

    responder = ConverseResponder(
        client=_FakeClient([LlmResponse(text='{"reply":"Greetings.","tone":"warm"}')]),
        settings=_settings(),
        telemetry=telemetry,
    )

    payload = responder.generate("hello", {"state": "exploration"})

    assert payload is not None
    calls = [event for event in sink.events if event.get("kind") == "llm_call"]
    assert len(calls) == 1
    assert calls[0]["domain"] == "converse"
    assert calls[0]["prompt_version"] == "converse.v2"
    assert calls[0]["context_token_estimate"] >= 0
