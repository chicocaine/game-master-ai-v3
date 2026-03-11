from __future__ import annotations

from game.core.action import Action
from game.core.action_result import ActionResult
from game.core.enums import ActionType
from game.catalog.models import Catalog
from game.cli import session_view
from game.states.game_session import GameSession


LIFECYCLE_EVENT_TYPES = {
    "action_submitted",
    "action_validated",
    "action_resolved",
}


def render_help(live_llm: bool = False) -> str:
    if live_llm:
        return "\n".join(
            [
                "Commands:",
                "Type plain text to drive the LLM loop (player -> parser -> route -> engine -> narration).",
                "/help",
                "/state",
                "/party",
                "/players",
                "/dungeons",
                "/room",
                "/encounter",
                "/add <player_template_id>",
                "/choose <dungeon_id>",
                "/start",
                "/save [session_id]",
                "/load <session_id>",
                "/quit",
            ]
        )

    return "\n".join(
        [
            "Commands:",
            "/help",
            "/state",
            "/party",
            "/players",
            "/dungeons",
            "/add <player_template_id>",
            "/choose <dungeon_id>",
            "/start",
            "/room",
            "/move <room_id>",
            "/rest <short|long>",
            "/encounter",
            "/attack <attack_id> <target_id> [more_target_ids...]",
            "/cast <spell_id> <target_id> [more_target_ids...]",
            "/end",
            "/save [session_id]",
            "/load <session_id>",
            "/quit",
        ]
    )


def render_player_templates(catalog: Catalog) -> str:
    if not catalog.player_templates:
        return "No player templates found."
    lines = ["Player templates:"]
    for template_id, template in sorted(catalog.player_templates.items()):
        player = template.player_seed
        lines.append(f"- {template_id}: {player.name} ({player.race.name} {player.archetype.name})")
    return "\n".join(lines)


def render_dungeons(session: GameSession) -> str:
    if not session.available_dungeons:
        return "No dungeons available."
    selected_id = session.dungeon.id if session.dungeon is not None else ""
    lines = ["Dungeons:"]
    for dungeon in session.available_dungeons:
        marker = "*" if dungeon.id == selected_id else "-"
        lines.append(f"{marker} {dungeon.id}: {dungeon.name} ({dungeon.difficulty.value})")
    return "\n".join(lines)


def render_state(session: GameSession) -> str:
    return "\n".join(session_view.state_lines(session))


def render_party(session: GameSession) -> str:
    return "\n".join(session_view.party_lines(session))


def render_room(session: GameSession) -> str:
    return "\n".join(session_view.room_lines(session))


def render_encounter(session: GameSession) -> str:
    lines = session_view.encounter_lines(session)
    actor_id = session_view.current_actor_id(session)
    if actor_id.startswith("player_"):
        actor = next((player for player in session.party if player.player_instance_id == actor_id), None)
        if actor is not None:
            attack_ids = ", ".join(attack.id for attack in actor.merged_attacks) or "none"
            spell_ids = ", ".join(spell.id for spell in actor.merged_spells) or "none"
            lines.append(f"Available attacks: {attack_ids}")
            lines.append(f"Available spells: {spell_ids}")
    return "\n".join(lines)


def _render_event(event: dict) -> str:
    event_type = str(event.get("type", "event"))
    if event_type == "converse":
        message = str(event.get("message", "")).strip()
        return f"Converse: {message}" if message else "Converse"
    if event_type == "turn_started":
        return f"Turn started: {event.get('actor_instance_id', '')}"
    if event_type == "turn_ended":
        return f"Turn ended: {event.get('actor_instance_id', '')}"
    if event_type == "turn_skipped":
        return f"Turn skipped: {event.get('actor_instance_id', '')} ({event.get('reason', 'unknown')})"
    if event_type == "attack_hit":
        return f"Attack hit: {event.get('actor_instance_id', '')} -> {event.get('target_instance_id', '')}"
    if event_type == "attack_missed":
        return f"Attack missed: {event.get('actor_instance_id', '')} -> {event.get('target_instance_id', '')}"
    if event_type == "damage_applied":
        return f"Damage: {event.get('target_instance_id', '')} lost {event.get('amount', 0)} HP"
    if event_type == "healing_applied":
        return f"Healing: {event.get('target_instance_id', '')} recovered {event.get('amount', 0)} HP"
    if event_type == "reward_granted":
        return f"Reward: +{event.get('amount', 0)} points"
    if event_type == "encounter_ended":
        return f"Encounter cleared: {event.get('encounter_id', '')}"
    return f"Event: {event_type}"


def render_action_feedback(
    action: Action,
    result: ActionResult,
    session: GameSession,
    events: list[dict],
    debug: bool = False,
) -> str:
    lines: list[str] = []
    if result.errors:
        lines.append("Action failed:")
        for error in result.errors:
            lines.append(f"- {error}")
        return "\n".join(lines)

    lines.append(f"Action completed: {action.type.value}")

    semantic_events = [event for event in events if event.get("type") not in LIFECYCLE_EVENT_TYPES]
    for event in semantic_events:
        lines.append(_render_event(event))

    if debug and events:
        lines.append(f"Debug: {events}")

    if action.type in {ActionType.CREATE_PLAYER, ActionType.REMOVE_PLAYER, ActionType.EDIT_PLAYER}:
        lines.append(render_party(session))
    elif action.type is ActionType.CHOOSE_DUNGEON:
        selected = session.dungeon.id if session.dungeon is not None else "none"
        lines.append(f"Selected dungeon: {selected}")
    elif action.type is ActionType.START:
        lines.append(render_state(session))
    elif session.state.value == "exploration":
        lines.append(render_room(session))
    elif session.state.value == "encounter":
        lines.append(render_encounter(session))
    else:
        lines.append(render_state(session))

    return "\n".join(lines)


def render_message(message: str) -> str:
    return str(message).strip()