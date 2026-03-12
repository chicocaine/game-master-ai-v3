from dataclasses import dataclass
from typing import Any, List

from game.engine.interfaces import ActionProvider, Narrator
from game.llm.config import LlmSettings
from game.llm.converse import ConverseResponder
from game.llm.narrator.llm_narrator import LlmNarrator
from game.llm.providers.enemy_llm_provider import EnemyLlmActionProvider
from game.llm.providers.player_intent_provider import PlayerIntentLlmProvider
from game.llm.telemetry import InMemoryLlmTelemetrySink, JsonlLlmTelemetrySink, LlmMetricsTracker, LlmTelemetry, LlmTelemetrySink


@dataclass(frozen=True)
class LlmRuntimeBundle:
    player_provider: PlayerIntentLlmProvider
    enemy_provider: EnemyLlmActionProvider
    narrator: LlmNarrator
    converse_responder: ConverseResponder
    telemetry: LlmTelemetry
    metrics: LlmMetricsTracker
    in_memory_sink: InMemoryLlmTelemetrySink | None


@dataclass(frozen=True)
class LlmClients:
    player_intent: Any
    enemy_ai: Any
    narration: Any
    converse: Any


def create_shared_telemetry(
    base_dir: str = "logs/events",
    enable_jsonl_sink: bool = True,
    enable_in_memory_sink: bool = False,
) -> tuple[LlmTelemetry, LlmMetricsTracker, InMemoryLlmTelemetrySink | None]:
    sinks: List[LlmTelemetrySink] = []

    if enable_jsonl_sink:
        sinks.append(JsonlLlmTelemetrySink(base_dir=base_dir))

    metrics = LlmMetricsTracker()
    sinks.append(metrics)

    memory_sink: InMemoryLlmTelemetrySink | None = None
    if enable_in_memory_sink:
        memory_sink = InMemoryLlmTelemetrySink()
        sinks.append(memory_sink)

    return LlmTelemetry(sinks=sinks), metrics, memory_sink


def create_llm_runtime_bundle(
    settings: LlmSettings,
    clients: LlmClients,
    telemetry_base_dir: str = "logs/events",
    enable_jsonl_telemetry: bool = True,
    enable_in_memory_telemetry: bool = False,
) -> LlmRuntimeBundle:
    telemetry, metrics, memory_sink = create_shared_telemetry(
        base_dir=telemetry_base_dir,
        enable_jsonl_sink=enable_jsonl_telemetry,
        enable_in_memory_sink=enable_in_memory_telemetry,
    )

    converse_responder = ConverseResponder(
        client=clients.converse,
        settings=settings,
        telemetry=telemetry,
    )

    player_provider = PlayerIntentLlmProvider(
        client=clients.player_intent,
        settings=settings,
        telemetry=telemetry,
    )

    enemy_provider = EnemyLlmActionProvider(
        client=clients.enemy_ai,
        settings=settings,
        telemetry=telemetry,
    )

    narrator = LlmNarrator(
        client=clients.narration,
        settings=settings,
        telemetry=telemetry,
    )

    return LlmRuntimeBundle(
        player_provider=player_provider,
        enemy_provider=enemy_provider,
        narrator=narrator,
        converse_responder=converse_responder,
        telemetry=telemetry,
        metrics=metrics,
        in_memory_sink=memory_sink,
    )


def build_provider_chain(
    player_provider: PlayerIntentLlmProvider,
    enemy_provider: EnemyLlmActionProvider,
    system_provider: ActionProvider | None = None,
) -> List[ActionProvider]:
    providers: List[ActionProvider] = [player_provider]
    if system_provider is not None:
        providers.append(system_provider)
    providers.append(enemy_provider)
    return providers


def bundle_narrator(bundle: LlmRuntimeBundle) -> Narrator:
    return bundle.narrator
