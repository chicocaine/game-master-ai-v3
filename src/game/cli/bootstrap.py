from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable
from uuid import uuid4

from game.cli.persistence import JsonFilePersistence
from game.cli.provider import InteractiveCliProvider, LiveLlmCliProvider
from game.engine.interfaces import EngineContext
from game.llm.converse import ConverseResponder
from game.llm.bootstrap import build_provider_chain, create_llm_runtime_bundle
from game.llm.config import load_llm_settings
from game.llm.live_clients import create_live_llm_clients
from game.engine.providers import TurnAwareEnemyStubProvider
from game.engine.sinks import InMemoryEventSink, SessionLogSink
from game.factories.game_factory import GameFactory
from game.data.data_loader import load_game_catalog


@dataclass
class CliRuntime:
    session: object
    ctx: EngineContext
    persistence: JsonFilePersistence
    cli_provider: InteractiveCliProvider
    providers: list[object]
    step_sink: InMemoryEventSink
    event_sinks: list[object]
    narrator: object | None = None
    converse_responder: ConverseResponder | None = None
    live_llm: bool = False


def bootstrap_cli_runtime(
    data_dir: str | Path = "data",
    schema_dir: str | Path | None = None,
    persistence_dir: str | Path | None = None,
    session_id: str | None = None,
    seed: int = 5,
    debug: bool = False,
    live_llm: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> CliRuntime:
    catalog = load_game_catalog(data_dir=data_dir, schema_dir=schema_dir, validate_schema=True)
    session = GameFactory.create_session(catalog=catalog, seed=seed)
    ctx = EngineContext(session_id=session_id or f"cli_{uuid4().hex[:8]}", step_count=0, seed=seed)
    resolved_persistence_dir = str(
        persistence_dir
        or os.getenv("GAME_MASTER_AI_PERSISTENCE_DIR", "logs/checkpoints")
    )
    persistence = JsonFilePersistence(base_dir=resolved_persistence_dir, catalog=catalog)
    narrator = None
    if live_llm:
        settings = load_llm_settings(require_api_key=False)
        clients = create_live_llm_clients(settings)
        llm_bundle = create_llm_runtime_bundle(settings=settings, clients=clients)
        cli_provider = LiveLlmCliProvider(
            input_fn=input_fn,
            output_fn=output_fn,
            persistence=persistence,
            debug=debug,
            player_provider=llm_bundle.player_provider,
        )
        providers = build_provider_chain(
            player_provider=llm_bundle.player_provider,
            enemy_provider=llm_bundle.enemy_provider,
            system_provider=cli_provider,
        )
        narrator = llm_bundle.narrator
        converse_responder = llm_bundle.converse_responder
    else:
        cli_provider = InteractiveCliProvider(
            input_fn=input_fn,
            output_fn=output_fn,
            persistence=persistence,
            debug=debug,
        )
        providers = [TurnAwareEnemyStubProvider(), cli_provider]
        converse_responder = None

    step_sink = InMemoryEventSink()
    event_sinks = [step_sink, SessionLogSink()]
    return CliRuntime(
        session=session,
        ctx=ctx,
        persistence=persistence,
        cli_provider=cli_provider,
        providers=providers,
        step_sink=step_sink,
        event_sinks=event_sinks,
        narrator=narrator,
        converse_responder=converse_responder,
        live_llm=live_llm,
    )