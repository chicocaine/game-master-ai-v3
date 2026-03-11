from __future__ import annotations

from game.enums import GameState
from game.states.game_session import GameSession


def current_actor_id(session: GameSession) -> str:
    if session.state is not GameState.ENCOUNTER:
        return ""
    turn_order = getattr(session.encounter, "turn_order", [])
    turn_index = getattr(session.encounter, "current_turn_index", -1)
    if not isinstance(turn_order, list) or turn_index < 0 or turn_index >= len(turn_order):
        return ""
    return str(turn_order[turn_index])


def party_lines(session: GameSession) -> list[str]:
    if not session.party:
        return ["Party: empty"]
    lines = ["Party:"]
    for player in session.party:
        lines.append(
            f"- {player.player_instance_id}: {player.name} HP {player.hp}/{player.max_hp} AC {player.effective_ac} Slots {player.spell_slots}/{player.max_spell_slots}"
        )
    return lines


def room_lines(session: GameSession) -> list[str]:
    room = session.exploration.current_room
    if room is None:
        return ["Room: none"]

    uncleared_encounters = [encounter for encounter in room.encounters if not encounter.cleared]
    lines = [
        f"Room: {room.id} ({room.name})",
        f"Description: {room.description}",
        f"Connections: {', '.join(room.connections) if room.connections else 'none'}",
        f"Rest options: {', '.join(rest.value for rest in room.allowed_rests) if room.allowed_rests else 'none'}",
        f"Uncleared encounters: {len(uncleared_encounters)}",
    ]
    return lines


def encounter_lines(session: GameSession) -> list[str]:
    encounter = session.encounter.current_encounter
    if encounter is None:
        return ["Encounter: none"]

    actor_id = current_actor_id(session)
    lines = [
        f"Encounter: {encounter.id} ({encounter.name})",
        f"Description: {encounter.description}",
        f"Current turn: {actor_id or 'unknown'}",
        "Enemies:",
    ]
    for enemy in encounter.enemies:
        lines.append(
            f"- {enemy.enemy_instance_id}: {enemy.name} HP {enemy.hp}/{enemy.max_hp} AC {enemy.effective_ac}"
        )
    return lines


def state_lines(session: GameSession) -> list[str]:
    lines = [f"State: {session.state.value}", f"Points: {session.points}"]
    if session.state is GameState.PREGAME:
        lines.extend(party_lines(session))
        selected = session.dungeon.id if session.dungeon is not None else "none"
        lines.append(f"Selected dungeon: {selected}")
        return lines
    if session.state is GameState.EXPLORATION:
        lines.extend(room_lines(session))
        return lines
    if session.state is GameState.ENCOUNTER:
        lines.extend(encounter_lines(session))
        return lines
    return lines