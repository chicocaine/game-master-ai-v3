from dataclasses import dataclass
from types import SimpleNamespace

from game.engine.interfaces import EngineContext
from game.engine.providers import TurnAwareEnemyStubProvider
from game.enums import GameState
from game.llm.bootstrap import LlmClients, build_provider_chain, create_llm_runtime_bundle
from game.llm.config import load_llm_settings
from game.llm.contracts import LlmResponse


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
            "LLM_TEMPERATURE_ENEMY": "0.2",
            "LLM_MAX_TOKENS_ENEMY": "128",
            "LLM_TEMPERATURE_NARRATION": "0.6",
            "LLM_MAX_TOKENS_NARRATION": "128",
            "LLM_TEMPERATURE_CONVERSATION": "0.4",
            "LLM_MAX_TOKENS_CONVERSATION": "128",
        }
    )


def _session() -> _SessionStub:
    return _SessionStub(
        state=GameState.EXPLORATION,
        party=[SimpleNamespace(player_instance_id="player_1", hp=10, max_hp=10)],
        exploration=SimpleNamespace(current_room=SimpleNamespace(id="room_1", is_cleared=False)),
        encounter=SimpleNamespace(turn_order=["player_1", "enemy_1"], current_turn_index=0),
    )


def test_create_llm_runtime_bundle_wires_shared_telemetry_and_ordered_providers(tmp_path):
    bundle = create_llm_runtime_bundle(
        settings=_settings(),
        clients=LlmClients(
            player_intent=_FakeClient(
                [LlmResponse(text='{"type":"converse","parameters":{"message":"hello"},"reasoning":"Input is conversational and requires dialogue."}')]
            ),
            enemy_ai=_FakeClient(
                [LlmResponse(text='{"type":"end_turn","actor_instance_id":"enemy_1","parameters":{},"reasoning":"No better tactical option available."}')]
            ),
            narration=_FakeClient([LlmResponse(text='{"text":"Narration.","reasoning":"A concise transition summary fits the event."}')]),
            converse=_FakeClient(
                [LlmResponse(text='{"reply":"GM reply.","reasoning":"Responding directly to the player question advances play.","tone":"calm"}')]
            ),
        ),
        telemetry_base_dir=str(tmp_path / "events"),
        enable_jsonl_telemetry=True,
        enable_in_memory_telemetry=True,
    )

    # All runtime components should share one telemetry object.
    assert bundle.player_provider.telemetry is bundle.telemetry
    assert bundle.enemy_provider.telemetry is bundle.telemetry
    assert bundle.narrator.telemetry is bundle.telemetry
    assert bundle.converse_responder.telemetry is bundle.telemetry

    system_provider = TurnAwareEnemyStubProvider()
    provider_chain = build_provider_chain(
        player_provider=bundle.player_provider,
        system_provider=system_provider,
        enemy_provider=bundle.enemy_provider,
    )

    assert provider_chain[0] is bundle.player_provider
    assert provider_chain[1] is system_provider
    assert provider_chain[2] is bundle.enemy_provider

    bundle.player_provider.enqueue("hello", actor_instance_id="player_1")
    action = bundle.player_provider.next_action(_session(), EngineContext(session_id="boot_1"))
    assert action is not None

    assert bundle.in_memory_sink is not None
    assert any(event.get("kind") == "llm_call" for event in bundle.in_memory_sink.events)
