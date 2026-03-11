from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from game.cli.bootstrap import bootstrap_cli_runtime
from game.cli.renderer import render_action_feedback, render_encounter, render_help, render_message, render_state
from game.engine.loop import run_engine_loop
from game.enums import GameState


def _emit(output_fn: Callable[[str], None], message: str) -> None:
    text = str(message or "").strip()
    if text:
        output_fn(text)


def _should_auto_start_room_encounter(session) -> bool:
    if session.state is not GameState.EXPLORATION:
        return False
    if session.exploration.current_room is None:
        return False
    if session.encounter.current_encounter is not None:
        return False
    return any(not encounter.cleared for encounter in session.exploration.current_room.encounters)


def run_cli(
    data_dir: str | Path = "data",
    schema_dir: str | Path | None = None,
    session_id: str | None = None,
    seed: int = 5,
    debug: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    runtime = bootstrap_cli_runtime(
        data_dir=data_dir,
        schema_dir=schema_dir,
        session_id=session_id,
        seed=seed,
        debug=debug,
        input_fn=input_fn,
        output_fn=output_fn,
    )

    _emit(output_fn, "CLI engine ready.")
    _emit(output_fn, f"Session: {runtime.ctx.session_id}")
    _emit(output_fn, render_help())
    _emit(output_fn, render_state(runtime.session))

    while True:
        if _should_auto_start_room_encounter(runtime.session):
            result = runtime.session.start_room_encounter()
            if result.errors:
                _emit(output_fn, render_message("\n".join(result.errors)))
                return 1
            _emit(output_fn, "Encounter started.")
            _emit(output_fn, render_encounter(runtime.session))

        outcome = run_engine_loop(
            session=runtime.session,
            providers=runtime.providers,
            event_sinks=runtime.event_sinks,
            narrator=None,
            persistence=runtime.persistence,
            ctx=runtime.ctx,
            max_steps=1,
        )

        step_events = runtime.step_sink.all_events()
        runtime.step_sink.clear()

        if outcome.last_action is not None and outcome.last_result is not None:
            _emit(
                output_fn,
                render_action_feedback(
                    action=outcome.last_action,
                    result=outcome.last_result,
                    session=runtime.session,
                    events=step_events,
                    debug=debug,
                ),
            )

        if runtime.cli_provider.quit_requested:
            _emit(output_fn, "CLI session ended.")
            return 0

        load_request = runtime.cli_provider.pop_load_request()
        if load_request is not None:
            restored = runtime.persistence.load(load_request)
            if restored is None:
                _emit(output_fn, f"No saved session '{load_request}' was found.")
            else:
                runtime.session = restored
                runtime.ctx.session_id = load_request
                _emit(output_fn, f"Loaded session: {load_request}")
                _emit(output_fn, render_state(runtime.session))
            continue

        if outcome.stopped_reason == "postgame":
            _emit(output_fn, "Run finished.")
            _emit(output_fn, render_state(runtime.session))
            return 0

        if outcome.stopped_reason == "idle":
            _emit(output_fn, "CLI session ended.")
            return 0

    return 0