"""Single-step execution and state rendering helpers for the Gradio UI.

`step_once` drives one engine tick and returns updated stream/panel text.
State panel helpers produce plain text for the four Column-3 blocks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.cli.parser import parse_cli_input
from game.cli.renderer import (
    _render_event,
    render_action_feedback,
    render_dungeons,
    render_encounter,
    render_help,
    render_message,
    render_party,
    render_player_templates,
    render_room,
    render_state,
)
from game.cli.session_view import current_actor_id
from game.core.action import Action, create_action
from game.core.enums import ActionType
from game.engine.loop import run_engine_loop
from game.enums import GameState, RestType
from game.factories.game_factory import GameFactory
from game.llm.routing import build_state_summary

if TYPE_CHECKING:
    from ui.gradio_bootstrap import GradioRuntime

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data container returned after each step
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    chat_history: list
    event_stream: str
    action_stream: str
    reasoning_stream: str
    block_1: str
    block_2: str
    block_3: str
    block_4: str


# ─────────────────────────────────────────────────────────────────────────────
# Input → Action translation (stub / slash-command mode)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_text_to_action(text: str, session) -> Action | None:
    """Convert a raw text string to an engine Action for stub (non-LLM) mode.

    Slash commands mirror the CLI.  Plain text is treated as a CONVERSE action.
    """
    command = parse_cli_input(text)
    if command is None:
        return None

    # Plain text → converse
    if command.name == "text":
        actor_id = current_actor_id(session) or (
            session.party[0].player_instance_id if session.party else "system"
        )
        return create_action(
            action_type=ActionType.CONVERSE,
            parameters={"message": text},
            actor_instance_id=actor_id,
        )

    # Slash commands
    if command.name == "add":
        catalog = getattr(session, "catalog", None)
        if catalog is None or not command.args:
            return None
        template_id = command.args[0]
        if template_id not in catalog.player_templates:
            return None
        player = catalog.player_templates[template_id].instantiate_player()
        return create_action(
            action_type=ActionType.CREATE_PLAYER,
            actor_instance_id="system",
            parameters={
                "id": player.id,
                "name": player.name,
                "description": player.description,
                "race": player.race.id,
                "archetype": player.archetype.id,
                "weapons": [weapon.id for weapon in list(player.weapons)],
            },
        )

    if command.name == "choose" and command.args:
        return create_action(ActionType.CHOOSE_DUNGEON, {"dungeon": command.args[0]}, actor_instance_id="system")

    if command.name == "start":
        return create_action(ActionType.START, {}, actor_instance_id="system")

    if command.name == "move":
        if not command.args or session.state is not GameState.EXPLORATION:
            return None
        actor_id = session.party[0].player_instance_id if session.party else "system"
        return create_action(ActionType.MOVE, {"destination_room_id": command.args[0]}, actor_instance_id=actor_id)

    if command.name == "rest":
        if not command.args or session.state is not GameState.EXPLORATION:
            return None
        try:
            rest_type = RestType(command.args[0].lower())
        except ValueError:
            return None
        actor_id = session.party[0].player_instance_id if session.party else "system"
        return create_action(ActionType.REST, {"rest_type": rest_type.value}, actor_instance_id=actor_id)

    if command.name in {"attack", "cast"}:
        if session.state is not GameState.ENCOUNTER or len(command.args) < 2:
            return None
        actor_id = current_actor_id(session)
        if not actor_id.startswith("player_"):
            return None
        if command.name == "attack":
            key, atype = "attack_id", ActionType.ATTACK
        else:
            key, atype = "spell_id", ActionType.CAST_SPELL
        raw_targets = list(command.args[1:])
        target_value = raw_targets if len(raw_targets) > 1 else raw_targets[0]
        return create_action(atype, {key: command.args[0], "target_instance_ids": target_value}, actor_instance_id=actor_id)

    if command.name == "end":
        if session.state is not GameState.ENCOUNTER:
            return None
        actor_id = current_actor_id(session)
        if not actor_id.startswith("player_"):
            return None
        return create_action(ActionType.END_TURN, {}, actor_instance_id=actor_id)

    return None


def _command_output_only(runtime: "GradioRuntime", command) -> str | None:
    """Handle non-action commands and return text output when handled."""
    if command.name == "help":
        return render_help(live_llm=runtime.live_llm)
    if command.name == "state":
        return render_state(runtime.session)
    if command.name == "party":
        return render_party(runtime.session)
    if command.name == "players":
        catalog = getattr(runtime.session, "catalog", None)
        return render_player_templates(catalog) if catalog is not None else "Catalog unavailable."
    if command.name == "dungeons":
        return render_dungeons(runtime.session)
    if command.name == "room":
        return render_room(runtime.session)
    if command.name == "encounter":
        return render_encounter(runtime.session)
    if command.name == "save":
        target_session_id = command.args[0] if command.args else runtime.ctx.session_id
        try:
            file_path = runtime.persistence.save_manual_snapshot(runtime.session, runtime.ctx, session_id=target_session_id)
        except Exception:
            logger.exception(
                "Manual save command failed.",
                extra={"session_id": runtime.ctx.session_id, "target_session_id": target_session_id},
            )
            return "Save failed. Session contains non-serializable objects in current snapshot state."
        return render_message(f"Saved session to {file_path.resolve()}")
    if command.name == "load":
        if not command.args:
            return "Usage: /load <session_id>"
        try:
            restored = runtime.persistence.load(command.args[0])
        except Exception:
            logger.exception(
                "Load command failed.",
                extra={"session_id": runtime.ctx.session_id, "target_session_id": command.args[0]},
            )
            return "Load failed. The snapshot may be invalid or incompatible."
        if restored is None:
            return f"No saved session '{command.args[0]}' was found."
        runtime.session = restored
        runtime.ctx.session_id = command.args[0]
        runtime.step_count = 0
        runtime.step_sink.clear()
        runtime.event_stream_text = ""
        runtime.action_stream_text = ""
        runtime.reasoning_stream_text = ""
        return f"Loaded session: {command.args[0]}"
    if command.name == "restart":
        runtime.session = GameFactory.create_session(catalog=runtime.session.catalog, seed=runtime.ctx.seed)
        runtime.ctx.step_count = 0
        runtime.step_count = 0
        runtime.step_sink.clear()
        runtime.event_stream_text = ""
        runtime.action_stream_text = ""
        runtime.reasoning_stream_text = ""
        if runtime.player_provider is not None:
            if hasattr(runtime.player_provider, "queue") and hasattr(runtime.player_provider.queue, "clear"):
                runtime.player_provider.queue.clear()
            if hasattr(runtime.player_provider, "timeline") and hasattr(runtime.player_provider.timeline, "clear"):
                runtime.player_provider.timeline.clear()
        if runtime.narrator is not None and hasattr(runtime.narrator, "timeline") and hasattr(runtime.narrator.timeline, "clear"):
            runtime.narrator.timeline.clear()
        if runtime.converse_responder is not None and hasattr(runtime.converse_responder, "timeline") and hasattr(runtime.converse_responder.timeline, "clear"):
            runtime.converse_responder.timeline.clear()
        return "Session restarted."
    if command.name == "quit":
        return "Web UI does not support /quit. Close the browser tab or stop the process."
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Stream helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_event_stream_entry(step: int, events: list) -> str:
    if not events:
        return ""
    lines = [f"[step {step}]"]
    for event in events:
        lines.append("  " + _render_event(event))
    return "\n".join(lines) + "\n"


def _format_action_stream_entry(step: int, action: Action | None, result) -> str:
    if action is None:
        return ""
    actor = getattr(action, "actor_instance_id", "?")
    params = getattr(action, "parameters", {}) or {}
    ok = getattr(result, "ok", None)
    status = "ok" if ok else "err"
    try:
        params_str = json.dumps(params, ensure_ascii=False, default=str)
    except Exception:
        params_str = repr(params)
    return f"[step {step}] [{actor}] {action.type.value} {params_str} ({status})\n"


def _format_reasoning_stream_entry(step: int, action: Action | None, narration: str | None, converse_reply: str | None) -> str:
    lines = []
    if action is not None:
        reasoning = str(getattr(action, "reasoning", "") or "").strip()
        metadata = dict(getattr(action, "metadata", {}) or {})
        provider = metadata.get("provider", "")
        if reasoning and (provider == "player_intent_llm" or reasoning):
            lines.append(f"[step {step}] [parser] {reasoning}")
        converse_meta = metadata.get("converse_response", {})
        if converse_meta:
            tone = converse_meta.get("tone", "")
            cr = str(converse_meta.get("reasoning", "")).strip()
            if cr:
                lines.append(f"[step {step}] [converse] tone={tone} {cr}")
    if narration:
        lines.append(f"[step {step}] [narrator] {narration}")
    if converse_reply:
        lines.append(f"[step {step}] [converse_reply] {converse_reply}")
    return ("\n".join(lines) + "\n") if lines else ""


# ─────────────────────────────────────────────────────────────────────────────
# Column 3 — state panel blocks
# ─────────────────────────────────────────────────────────────────────────────

def _party_status(session) -> str:
    party = getattr(session, "party", [])
    if not party:
        return "Party: empty"
    lines = ["Party:"]
    for p in party:
        lines.append(
            f"  {p.player_instance_id}: {p.name} HP {p.hp}/{p.max_hp} "
            f"AC {p.effective_ac} Slots {p.spell_slots}/{p.max_spell_slots}"
        )
    return "\n".join(lines)


def render_state_blocks(session) -> tuple[str, str, str, str]:
    """Return (block_1, block_2, block_3, block_4) text for Column 3."""
    state = getattr(session, "state", None)

    if state is GameState.PREGAME:
        # Block 1: state + dungeon
        dungeon = getattr(session, "dungeon", None)
        dungeon_id = getattr(dungeon, "id", "none") if dungeon else "none"
        dungeon_name = getattr(dungeon, "name", "") if dungeon else ""
        b1 = f"State: {state.value}\nSelected dungeon: {dungeon_id}" + (f" ({dungeon_name})" if dungeon_name else "")

        # Block 2: current party
        b2 = _party_status(session)

        # Block 3: available dungeons
        available = getattr(session, "available_dungeons", []) or []
        if available:
            lines = ["Available dungeons:"]
            for d in available:
                lines.append(f"  {d.id}: {d.name} ({d.difficulty.value})")
            b3 = "\n".join(lines)
        else:
            b3 = "No dungeons available."

        # Block 4: player templates
        catalog = getattr(session, "catalog", None)
        templates = getattr(catalog, "player_templates", {}) if catalog else {}
        if templates:
            lines = ["Player templates:"]
            for tid, tmpl in sorted(templates.items()):
                p = tmpl.player_seed
                lines.append(f"  {tid}: {p.name} ({p.race.name} {p.archetype.name})")
            b4 = "\n".join(lines)
        else:
            b4 = "No player templates."

        return b1, b2, b3, b4

    if state is GameState.EXPLORATION:
        exploration = getattr(session, "exploration", None)
        room = getattr(exploration, "current_room", None) if exploration else None

        if room is not None:
            b1 = (
                f"Room: {room.id}\nName: {room.name}\n"
                f"Description: {room.description}"
            )
            connections = getattr(room, "connections", []) or []
            rests = getattr(room, "allowed_rests", []) or []
            b2 = (
                f"Connections: {', '.join(connections) or 'none'}\n"
                f"Rest options: {', '.join(r.value for r in rests) or 'none'}"
            )
            uncleared = [e for e in getattr(room, "encounters", []) if not e.cleared]
            b3 = f"Uncleared encounters: {len(uncleared)}"
        else:
            b1, b2, b3 = "Room: none", "", ""

        b4 = _party_status(session)
        return b1, b2, b3, b4

    if state is GameState.ENCOUNTER:
        encounter_state = getattr(session, "encounter", None)
        encounter = getattr(encounter_state, "current_encounter", None) if encounter_state else None
        actor_id = current_actor_id(session)

        if encounter is not None:
            turn_order = getattr(encounter_state, "turn_order", []) or []
            b1 = (
                f"Encounter: {encounter.id}\nCurrent turn: {actor_id or 'unknown'}\n"
                f"Turn order: {', '.join(turn_order)}"
            )
        else:
            b1 = "Encounter: none"

        # Block 2: player HP/slots
        b2 = _party_status(session)

        # Block 3: enemy HP/AC
        if encounter is not None:
            lines = ["Enemies:"]
            for e in getattr(encounter, "enemies", []):
                lines.append(
                    f"  {e.enemy_instance_id}: {e.name} HP {e.hp}/{e.max_hp} AC {e.effective_ac}"
                )
            b3 = "\n".join(lines)
        else:
            b3 = "No active encounter."

        # Block 4: current player's available moves
        if actor_id.startswith("player_"):
            player = next(
                (p for p in session.party if p.player_instance_id == actor_id), None
            )
            if player is not None:
                attacks = ", ".join(a.id for a in player.merged_attacks) or "none"
                spells = ", ".join(s.id for s in player.merged_spells) or "none"
                b4 = f"Available attacks: {attacks}\nAvailable spells: {spells}"
            else:
                b4 = ""
        else:
            b4 = f"Enemy turn: {actor_id}"

        return b1, b2, b3, b4

    if state is GameState.POSTGAME:
        postgame_state = getattr(session, "postgame", None)
        outcome = getattr(postgame_state, "outcome", None) if postgame_state else None
        b1 = f"State: {state.value}\nOutcome: {getattr(outcome, 'value', str(outcome))}"
        b2 = f"Points: {getattr(session, 'points', 0)}"
        b3 = ""
        b4 = "Type /restart or start a new session to play again."
        return b1, b2, b3, b4

    return f"State: {getattr(state, 'value', str(state))}", "", "", ""


# ─────────────────────────────────────────────────────────────────────────────
# Encounter auto-start helper (mirrors CLI logic)
# ─────────────────────────────────────────────────────────────────────────────

def _should_auto_start_encounter(session) -> bool:
    if session.state is not GameState.EXPLORATION:
        return False
    exploration = getattr(session, "exploration", None)
    if exploration is None or getattr(exploration, "current_room", None) is None:
        return False
    encounter_state = getattr(session, "encounter", None)
    if encounter_state is not None and getattr(encounter_state, "current_encounter", None) is not None:
        return False
    room = exploration.current_room
    return any(not enc.cleared for enc in getattr(room, "encounters", []))


def _publish_events(runtime: "GradioRuntime", events: list) -> None:
    if not events:
        return
    for sink in runtime.event_sinks:
        try:
            sink.publish(events, runtime.ctx)
        except Exception:
            logger.exception(
                "Gradio event sink publish failed.",
                extra={"sink": sink.__class__.__name__, "session_id": runtime.ctx.session_id},
            )


# ─────────────────────────────────────────────────────────────────────────────
# Converse / narration helpers (mirrors cli/app.py)
# ─────────────────────────────────────────────────────────────────────────────

def _build_converse_player_message(action: Action) -> str:
    message = str(getattr(action, "raw_input", "") or "").strip()
    if message:
        return message
    params = dict(getattr(action, "parameters", {}) or {})
    if "message" in params:
        return str(params["message"]).strip()
    return f"Action '{action.type.value}' was resolved."


def _build_converse_reasoning(action: Action, result, route_reason: str) -> str:
    event_types = [
        str(e.get("type", ""))
        for e in list(getattr(result, "events", []))
        if isinstance(e, dict)
    ]
    error_summary = "; ".join(list(getattr(result, "errors", [])))
    parts = [
        f"route={route_reason}",
        f"action_type={action.type.value}",
        f"ok={bool(getattr(result, 'ok', False))}",
    ]
    if error_summary:
        parts.append(f"errors={error_summary}")
    if event_types:
        parts.append(f"event_types={','.join(event_types)}")
    return " | ".join(parts)


def _invoke_converse(runtime: "GradioRuntime", action: Action, result, route_reason: str) -> str | None:
    if runtime.converse_responder is None:
        return None
    try:
        payload = runtime.converse_responder.generate(
            player_message=_build_converse_player_message(action),
            state_summary=build_state_summary(runtime.session),
            step_count=runtime.ctx.step_count,
            parser_reasoning=_build_converse_reasoning(action, result, route_reason=route_reason),
            parser_metadata={
                "route_reason": route_reason,
                "action_type": action.type.value,
                "action_parameters": dict(getattr(action, "parameters", {}) or {}),
                "errors": list(getattr(result, "errors", [])),
                "event_count": len(list(getattr(result, "events", []))),
                "state": runtime.session.state.value,
            },
        )
    except Exception:
        logger.exception(
            "Converse responder failed.",
            extra={"session_id": runtime.ctx.session_id, "route_reason": route_reason},
        )
        return None

    if not isinstance(payload, dict):
        return None

    # Attach reply metadata back to action so reasoning stream can read it
    meta = dict(getattr(action, "metadata", {}) or {})
    meta["converse_response"] = {
        "reply": str(payload.get("reply", "")),
        "reasoning": str(payload.get("reasoning", "")),
        "tone": str(payload.get("tone", "")),
        "metadata": dict(payload.get("metadata", {})),
    }
    action.metadata = meta

    reply = str(payload.get("reply", "")).strip()
    return reply or None


def _invoke_narration(runtime: "GradioRuntime", events: list) -> str | None:
    if runtime.narrator is None or not events:
        return None
    try:
        return runtime.narrator.narrate(events, runtime.session, runtime.ctx)
    except Exception:
        logger.exception(
            "Narrator failed.",
            extra={"session_id": runtime.ctx.session_id, "step_count": runtime.ctx.step_count},
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main step function
# ─────────────────────────────────────────────────────────────────────────────

def step_once(
    runtime: "GradioRuntime",
    user_input: str,
    chat_history: list,
    append_user_message: bool = True,
) -> StepResult:
    """Run one engine tick driven by `user_input`, return updated UI state."""

    step = runtime.step_count
    input_text = str(user_input or "").strip()
    chat_history = list(chat_history or [])
    if append_user_message:
        chat_history.append({"role": "user", "content": input_text})

    command = None
    try:
        command = parse_cli_input(input_text)
    except ValueError as exc:
        chat_history.append({"role": "assistant", "content": str(exc)})
        b1, b2, b3, b4 = render_state_blocks(runtime.session)
        return StepResult(
            chat_history=chat_history,
            event_stream=runtime.event_stream_text,
            action_stream=runtime.action_stream_text,
            reasoning_stream=runtime.reasoning_stream_text,
            block_1=b1,
            block_2=b2,
            block_3=b3,
            block_4=b4,
        )

    if command is None:
        b1, b2, b3, b4 = render_state_blocks(runtime.session)
        return StepResult(
            chat_history=chat_history,
            event_stream=runtime.event_stream_text,
            action_stream=runtime.action_stream_text,
            reasoning_stream=runtime.reasoning_stream_text,
            block_1=b1,
            block_2=b2,
            block_3=b3,
            block_4=b4,
        )

    output_only_text = None
    if command.name != "text":
        output_only_text = _command_output_only(runtime, command)
        if output_only_text is not None:
            chat_history.append({"role": "assistant", "content": output_only_text})
            b1, b2, b3, b4 = render_state_blocks(runtime.session)
            return StepResult(
                chat_history=chat_history,
                event_stream=runtime.event_stream_text,
                action_stream=runtime.action_stream_text,
                reasoning_stream=runtime.reasoning_stream_text,
                block_1=b1,
                block_2=b2,
                block_3=b3,
                block_4=b4,
            )

    # ── Route input into the provider ────────────────────────────────────────
    if runtime.live_llm and command.name == "text":
        # Live LLM: plain text goes to PlayerIntentLlmProvider.
        actor_id = current_actor_id(runtime.session) or (
            runtime.session.party[0].player_instance_id if runtime.session.party else ""
        )
        if runtime.player_provider is None:
            chat_history.append(
                {
                    "role": "assistant",
                    "content": "Live LLM parser is unavailable. Check your LLM configuration.",
                }
            )
            b1, b2, b3, b4 = render_state_blocks(runtime.session)
            return StepResult(
                chat_history=chat_history,
                event_stream=runtime.event_stream_text,
                action_stream=runtime.action_stream_text,
                reasoning_stream=runtime.reasoning_stream_text,
                block_1=b1,
                block_2=b2,
                block_3=b3,
                block_4=b4,
            )
        # When it's the enemy's turn in an ENCOUNTER, do NOT route user text into the
        # player intent LLM. The enemy_provider in the chain will generate the action
        # automatically (mirrors LiveLlmCliProvider._active_player_actor_id() in cli/provider.py).
        is_enemy_turn = (
            runtime.session.state is GameState.ENCOUNTER
            and actor_id.startswith("enemy_")
        )
        if not is_enemy_turn:
            runtime.player_provider.enqueue(input_text, actor_instance_id=actor_id)
    else:
        # Slash actions (or all input in deterministic mode) are translated directly.
        action = _parse_text_to_action(input_text, runtime.session)
        if action is not None:
            runtime.queue_provider.enqueue(action)
        else:
            # Unknown command — echo a hint back and return unchanged state
            chat_history.append({"role": "assistant", "content": "Unknown command. Use /help or type natural language."})
            b1, b2, b3, b4 = render_state_blocks(runtime.session)
            return StepResult(
                chat_history=chat_history,
                event_stream=runtime.event_stream_text,
                action_stream=runtime.action_stream_text,
                reasoning_stream=runtime.reasoning_stream_text,
                block_1=b1, block_2=b2, block_3=b3, block_4=b4,
            )

    # ── Auto-start encounter if already pending before this step ─────────────
    if _should_auto_start_encounter(runtime.session):
        enc_result = runtime.session.start_room_encounter()
        _publish_events(runtime, enc_result.events)
        enc_narration = _invoke_narration(runtime, enc_result.events) if runtime.live_llm else None
        if enc_narration:
            chat_history.append({"role": "assistant", "content": enc_narration})
        runtime.event_stream_text += _format_event_stream_entry(step, enc_result.events)

    # ── Run one engine step ───────────────────────────────────────────────────
    outcome = run_engine_loop(
        session=runtime.session,
        providers=runtime.providers,
        event_sinks=runtime.event_sinks,
        narrator=None,           # narration handled below for UI routing
        persistence=runtime.persistence,
        ctx=runtime.ctx,
        max_steps=1,
    )

    step_events = runtime.step_sink.all_events()
    runtime.step_sink.clear()

    # ── Auto-start encounter if this step moved into a room with enemies ────
    post_step_encounter_started = False
    post_step_encounter_events: list[dict] = []
    if _should_auto_start_encounter(runtime.session):
        post_step_enc_result = runtime.session.start_room_encounter()
        post_step_encounter_events = list(post_step_enc_result.events or [])
        _publish_events(runtime, post_step_encounter_events)
        enc_narration = _invoke_narration(runtime, post_step_encounter_events) if runtime.live_llm else None
        if enc_narration:
            chat_history.append({"role": "assistant", "content": enc_narration})
        post_step_encounter_started = True

    last_action: Action | None = outcome.last_action
    last_result = outcome.last_result

    # ── Build action feedback for chat (stub mode only) ─────────────────────
    if last_action is not None and last_result is not None:
        if not runtime.live_llm:
            feedback = render_action_feedback(
                action=last_action,
                result=last_result,
                session=runtime.session,
                events=step_events,
                debug=False,
            )
            if feedback.strip():
                chat_history.append({"role": "assistant", "content": feedback})

    # ── LLM routing: converse / narration ────────────────────────────────────
    narration_text: str | None = None
    converse_reply: str | None = None
    expected_route: str | None = None
    narration_attempted = False

    if runtime.live_llm and last_action is not None and last_result is not None:
        if last_action.type == ActionType.CONVERSE:
            expected_route = "converse"
            converse_reply = _invoke_converse(runtime, last_action, last_result, route_reason="intent_converse")
        elif runtime.session.state in {GameState.PREGAME, GameState.POSTGAME}:
            expected_route = "converse"
            converse_reply = _invoke_converse(runtime, last_action, last_result, route_reason="state_route_converse")
        elif runtime.session.state in {GameState.EXPLORATION, GameState.ENCOUNTER}:
            expected_route = "narration"
            if not post_step_encounter_started:
                narration_attempted = True
                narration_text = _invoke_narration(runtime, step_events)

        if converse_reply:
            chat_history.append({"role": "assistant", "content": converse_reply})
        if narration_text:
            chat_history.append({"role": "assistant", "content": narration_text})

        if expected_route == "converse" and not converse_reply:
            chat_history.append(
                {
                    "role": "assistant",
                    "content": "I couldn't generate a converse response right now. Check your live LLM configuration and try again.",
                }
            )
        if expected_route == "narration" and narration_attempted and step_events and not narration_text:
            chat_history.append(
                {
                    "role": "assistant",
                    "content": "I couldn't generate narration for that action right now. Check your live LLM configuration and try again.",
                }
            )

    # ── Update streams ────────────────────────────────────────────────────────
    step_event_batch = list(step_events)
    if post_step_encounter_events:
        step_event_batch.extend(post_step_encounter_events)

    runtime.event_stream_text += _format_event_stream_entry(step, step_event_batch)
    runtime.action_stream_text += _format_action_stream_entry(step, last_action, last_result)
    runtime.reasoning_stream_text += _format_reasoning_stream_entry(
        step, last_action, narration_text, converse_reply
    )
    runtime.step_count += 1

    # ── State panel (column 3) ────────────────────────────────────────────────
    b1, b2, b3, b4 = render_state_blocks(runtime.session)

    return StepResult(
        chat_history=chat_history,
        event_stream=runtime.event_stream_text,
        action_stream=runtime.action_stream_text,
        reasoning_stream=runtime.reasoning_stream_text,
        block_1=b1,
        block_2=b2,
        block_3=b3,
        block_4=b4,
    )
