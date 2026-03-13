"""Bootstrap utilities for the Gradio UI runtime.

Independent from the CLI runtime — no InteractiveCliProvider or CLI-specific
state is used here. Uses QueueActionProvider (stub mode) or the live LLM
provider chain (live_llm mode).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from game.cli.persistence import JsonFilePersistence
from game.data.data_loader import load_game_catalog
from game.engine.interfaces import EngineContext
from game.engine.providers import QueueActionProvider, TurnAwareEnemyStubProvider
from game.engine.sinks import InMemoryEventSink, SessionLogSink
from game.factories.game_factory import GameFactory
from game.llm.converse import ConverseResponder


logger = logging.getLogger(__name__)


@dataclass
class GradioRuntime:
    """Holds all runtime state for one Gradio UI session."""

    session: object
    ctx: EngineContext
    persistence: JsonFilePersistence
    queue_provider: QueueActionProvider
    player_provider: object | None
    providers: list
    step_sink: InMemoryEventSink
    event_sinks: list
    narrator: object | None = None
    converse_responder: ConverseResponder | None = None
    live_llm: bool = False
    llm_bootstrap_error: str = ""

    # Accumulated stream text (appended each step, never reset mid-session)
    event_stream_text: str = field(default="", compare=False)
    action_stream_text: str = field(default="", compare=False)
    reasoning_stream_text: str = field(default="", compare=False)
    step_count: int = field(default=0, compare=False)


def bootstrap_gradio_runtime(
    data_dir: str | Path = "data",
    schema_dir: str | Path | None = None,
    persistence_dir: str | Path | None = None,
    session_id: str | None = None,
    seed: int = 5,
    live_llm: bool = False,
    debug: bool = False,
) -> GradioRuntime:
    catalog = load_game_catalog(data_dir=data_dir, schema_dir=schema_dir, validate_schema=True)
    session = GameFactory.create_session(catalog=catalog, seed=seed)
    ctx = EngineContext(
        session_id=session_id or f"gradio_{uuid4().hex[:8]}",
        step_count=0,
        seed=seed,
    )
    resolved_persistence_dir = str(
        persistence_dir or os.getenv("GAME_MASTER_AI_PERSISTENCE_DIR", "logs/checkpoints")
    )
    persistence = JsonFilePersistence(base_dir=resolved_persistence_dir, catalog=catalog)

    queue_provider = QueueActionProvider()
    player_provider = None
    narrator = None
    converse_responder = None
    llm_bootstrap_error = ""

    if live_llm:
        try:
            from game.llm.bootstrap import build_provider_chain, create_llm_runtime_bundle
            from game.llm.config import load_llm_settings
            from game.llm.live_clients import create_live_llm_clients

            settings = load_llm_settings(require_api_key=False)
            clients = create_live_llm_clients(settings)
            llm_bundle = create_llm_runtime_bundle(settings=settings, clients=clients)

            providers = build_provider_chain(
                player_provider=llm_bundle.player_provider,
                enemy_provider=llm_bundle.enemy_provider,
                system_provider=queue_provider,
            )
            player_provider = llm_bundle.player_provider
            narrator = llm_bundle.narrator
            converse_responder = llm_bundle.converse_responder
        except Exception:
            llm_bootstrap_error = "Live LLM bootstrap failed. Check LLM provider/API key configuration."
            logger.exception(
                "Failed to initialise live LLM bundle; falling back to stub mode.",
                extra={"session_id": ctx.session_id},
            )
            providers = [TurnAwareEnemyStubProvider(), queue_provider]
            live_llm = False
    else:
        providers = [TurnAwareEnemyStubProvider(), queue_provider]

    step_sink = InMemoryEventSink()
    event_sinks: list = [step_sink, SessionLogSink()]

    return GradioRuntime(
        session=session,
        ctx=ctx,
        persistence=persistence,
        queue_provider=queue_provider,
        player_provider=player_provider,
        providers=providers,
        step_sink=step_sink,
        event_sinks=event_sinks,
        narrator=narrator,
        converse_responder=converse_responder,
        live_llm=live_llm,
        llm_bootstrap_error=llm_bootstrap_error,
    )
