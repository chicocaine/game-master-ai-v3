from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from game.cli.persistence import JsonFilePersistence
from game.cli.provider import InteractiveCliProvider
from game.engine.interfaces import EngineContext
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


def bootstrap_cli_runtime(
    data_dir: str | Path = "data",
    schema_dir: str | Path | None = None,
    session_id: str | None = None,
    seed: int = 5,
    debug: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> CliRuntime:
    catalog = load_game_catalog(data_dir=data_dir, schema_dir=schema_dir, validate_schema=True)
    session = GameFactory.create_session(catalog=catalog, seed=seed)
    ctx = EngineContext(session_id=session_id or f"cli_{uuid4().hex[:8]}", turn_index=0, seed=seed)
    persistence = JsonFilePersistence(catalog=catalog)
    cli_provider = InteractiveCliProvider(
        input_fn=input_fn,
        output_fn=output_fn,
        persistence=persistence,
        debug=debug,
    )
    step_sink = InMemoryEventSink()
    event_sinks = [step_sink, SessionLogSink()]
    providers = [TurnAwareEnemyStubProvider(), cli_provider]
    return CliRuntime(
        session=session,
        ctx=ctx,
        persistence=persistence,
        cli_provider=cli_provider,
        providers=providers,
        step_sink=step_sink,
        event_sinks=event_sinks,
    )