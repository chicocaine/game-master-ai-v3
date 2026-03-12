from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Sequence

from game.cli.bootstrap import bootstrap_cli_runtime
from game.cli.renderer import render_action_feedback, render_encounter, render_help, render_message, render_state
from game.engine.loop import run_engine_loop
from game.enums import GameState
from game.llm.debug_context import should_emit
from game.llm.routing import build_state_summary
from game.core.enums import ActionType
import json


logger = logging.getLogger(__name__)

_PREGAME_CONVERSE_FALLBACK_TYPES = frozenset({
    ActionType.CREATE_PLAYER,
    ActionType.EDIT_PLAYER,
    ActionType.REMOVE_PLAYER,
    ActionType.CHOOSE_DUNGEON,
})


def _emit(output_fn: Callable[[str], None], message: str) -> None:
    text = str(message or "").strip()
    if text:
        output_fn(text)


def _publish_runtime_events(runtime, events: list[dict]) -> None:
    if not events:
        return
    for sink in runtime.event_sinks:
        try:
            sink.publish(events, runtime.ctx)
        except Exception:
            logger.exception(
                "Runtime event sink publish failed; continuing.",
                extra={"sink": sink.__class__.__name__, "session_id": runtime.ctx.session_id},
            )
            continue


def _should_auto_start_room_encounter(session) -> bool:
    if session.state is not GameState.EXPLORATION:
        return False
    if session.exploration.current_room is None:
        return False
    if session.encounter.current_encounter is not None:
        return False
    return any(not encounter.cleared for encounter in session.exploration.current_room.encounters)


def _emit_parser_action_debug(output_fn: Callable[[str], None], action) -> None:
    metadata = dict(getattr(action, "metadata", {}) or {})
    if metadata.get("provider") != "player_intent_llm":
        return
    if not should_emit("player_intent"):
        return

    payload = action.to_dict() if hasattr(action, "to_dict") else {}
    action_type = str(payload.get("type", ""))
    actor_instance_id = str(payload.get("actor_instance_id", ""))
    reasoning = str(payload.get("reasoning", "")).strip()
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}

    concise = (
        f"game-master-ai[parser] type={action_type} actor={actor_instance_id} "
        f"params={json.dumps(parameters, ensure_ascii=False)}"
    )
    if reasoning:
        concise = f"{concise} reasoning={reasoning}"

    _emit(output_fn, concise)
    _emit(output_fn, f"game-master-ai[parser] {json.dumps(payload, ensure_ascii=False)}")


def run_cli(
    data_dir: str | Path = "data",
    schema_dir: str | Path | None = None,
    session_id: str | None = None,
    seed: int = 5,
    debug: bool = False,
    live_llm: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    def _bootstrap_fresh_runtime(current_session_id: str | None = None):
        return bootstrap_cli_runtime(
            data_dir=data_dir,
            schema_dir=schema_dir,
            session_id=current_session_id,
            seed=seed,
            debug=debug,
            live_llm=live_llm,
            input_fn=input_fn,
            output_fn=output_fn,
        )

    runtime = _bootstrap_fresh_runtime(session_id)

    _emit(output_fn, "CLI engine ready.")
    if runtime.live_llm:
        _emit(output_fn, "Live LLM mode enabled.")
    _emit(output_fn, f"Session: {runtime.ctx.session_id}")
    _emit(output_fn, render_help(live_llm=runtime.live_llm))
    _emit(output_fn, render_state(runtime.session))

    while True:
        if _should_auto_start_room_encounter(runtime.session):
            result = runtime.session.start_room_encounter()
            if result.errors:
                _emit(output_fn, render_message("\n".join(result.errors)))
                return 1
            _publish_runtime_events(runtime, result.events)
            try:
                runtime.persistence.save_manual_snapshot(runtime.session, runtime.ctx)
            except Exception:
                logger.exception(
                    "Manual snapshot save failed after auto encounter start.",
                    extra={"session_id": runtime.ctx.session_id},
                )
            _emit(output_fn, "Encounter started.")
            _emit(output_fn, render_encounter(runtime.session))
            if runtime.live_llm and runtime.narrator is not None and result.events:
                try:
                    narration_text = runtime.narrator.narrate(result.events, runtime.session, runtime.ctx)
                except Exception:
                    logger.exception(
                        "Narrator failed for encounter-start events.",
                        extra={"session_id": runtime.ctx.session_id},
                    )
                    narration_text = None
                if narration_text:
                    _emit(output_fn, f"game-master-ai[narrator] {narration_text}")

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
            if runtime.live_llm:
                _emit_parser_action_debug(output_fn, outcome.last_action)

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

            if runtime.live_llm and outcome.last_action.type.value == "converse":
                response_payload = None
                if runtime.converse_responder is not None:
                    player_message = str(outcome.last_action.raw_input or outcome.last_action.parameters.get("message", ""))
                    response_payload = runtime.converse_responder.generate(
                        player_message=player_message,
                        state_summary=build_state_summary(runtime.session),
                        step_count=runtime.ctx.step_count,
                        parser_reasoning=str(outcome.last_action.reasoning or ""),
                        parser_metadata=dict(outcome.last_action.metadata),
                    )
                if isinstance(response_payload, dict):
                    response_metadata = dict(outcome.last_action.metadata)
                    response_metadata["converse_response"] = {
                        "reply": str(response_payload.get("reply", "")),
                        "reasoning": str(response_payload.get("reasoning", "")),
                        "tone": str(response_payload.get("tone", "")),
                        "metadata": dict(response_payload.get("metadata", {})),
                    }
                    outcome.last_action.metadata = response_metadata
                    reply = str(response_payload.get("reply", "")).strip()
                    if reply:
                        _emit(output_fn, f"game-master-ai[converse] {reply}")
            elif (
                runtime.live_llm
                and outcome.last_result.errors
                and runtime.converse_responder is not None
                and outcome.last_action.type in _PREGAME_CONVERSE_FALLBACK_TYPES
            ):
                error_summary = "; ".join(outcome.last_result.errors)
                response_payload = runtime.converse_responder.generate(
                    player_message=str(outcome.last_action.raw_input or ""),
                    state_summary=build_state_summary(runtime.session),
                    step_count=runtime.ctx.step_count,
                    parser_reasoning=(
                        f"Action '{outcome.last_action.type.value}' was rejected by the game engine: {error_summary}"
                    ),
                    parser_metadata={
                        "action_type": outcome.last_action.type.value,
                        "errors": list(outcome.last_result.errors),
                        "action_parameters": dict(outcome.last_action.parameters),
                    },
                )
                if isinstance(response_payload, dict):
                    reply = str(response_payload.get("reply", "")).strip()
                    if reply:
                        _emit(output_fn, f"game-master-ai[converse] {reply}")

        if runtime.live_llm and runtime.narrator is not None and step_events:
            try:
                narration_text = runtime.narrator.narrate(step_events, runtime.session, runtime.ctx)
            except Exception:
                logger.exception(
                    "Narrator failed for step events.",
                    extra={"session_id": runtime.ctx.session_id, "step_count": runtime.ctx.step_count},
                )
                narration_text = None
            if narration_text:
                _emit(output_fn, f"game-master-ai[narrator] {narration_text}")

        if runtime.cli_provider.quit_requested:
            _emit(output_fn, "CLI session ended.")
            return 0

        if runtime.cli_provider.pop_restart_request():
            runtime = _bootstrap_fresh_runtime(runtime.ctx.session_id)
            _emit(output_fn, "Session restarted.")
            _emit(output_fn, render_state(runtime.session))
            continue

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
            runtime = _bootstrap_fresh_runtime(runtime.ctx.session_id)
            _emit(output_fn, "Run finished. Fresh pregame started.")
            _emit(output_fn, render_state(runtime.session))
            continue

        if outcome.stopped_reason == "idle":
            _emit(output_fn, "CLI session ended.")
            return 0

    return 0