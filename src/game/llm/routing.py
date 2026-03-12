from typing import Any, Dict

from game.enums import GameState
from game.llm.prompts import encounter, exploration, postgame, pregame


PromptModule = Any


def prompt_module_for_state(state: GameState) -> PromptModule:
    if state is GameState.PREGAME:
        return pregame
    if state is GameState.EXPLORATION:
        return exploration
    if state is GameState.ENCOUNTER:
        return encounter
    if state is GameState.POSTGAME:
        return postgame
    return exploration


def build_state_summary(session: Any) -> Dict[str, Any]:
    state_value = getattr(getattr(session, "state", None), "value", "")
    summary: Dict[str, Any] = {
        "state": state_value,
        "party_size": len(getattr(session, "party", [])),
        "points": int(getattr(session, "points", 0)),
    }

    dungeon = getattr(session, "dungeon", None)
    if dungeon is not None:
        summary["dungeon_id"] = str(getattr(dungeon, "id", ""))
        summary["dungeon_name"] = str(getattr(dungeon, "name", ""))

    if state_value == GameState.PREGAME.value:
        available_dungeons = []
        for dungeon_template in list(getattr(session, "available_dungeons", []) or []):
            available_dungeons.append(
                {
                    "id": str(getattr(dungeon_template, "id", "")),
                    "name": str(getattr(dungeon_template, "name", "")),
                }
            )
        summary["available_dungeons"] = available_dungeons

    if state_value == GameState.PREGAME.value:
        missing_requirements: list[str] = []
        if len(getattr(session, "party", [])) <= 0:
            missing_requirements.append("party")
        if dungeon is None:
            missing_requirements.append("dungeon")
        summary["can_start"] = len(missing_requirements) == 0
        if missing_requirements:
            summary["missing_requirements"] = missing_requirements

    if state_value in {GameState.EXPLORATION.value, GameState.ENCOUNTER.value}:
        exploration = getattr(session, "exploration", None)
        current_room = getattr(exploration, "current_room", None) if exploration is not None else None
        rooms_by_id = {
            str(getattr(room, "id", "")): room
            for room in list(getattr(dungeon, "rooms", []) or [])
            if str(getattr(room, "id", ""))
        }
        if current_room is not None:
            summary["current_room_id"] = str(getattr(current_room, "id", ""))
            summary["current_room_cleared"] = bool(getattr(current_room, "is_cleared", False))
            summary["current_room"] = {
                "id": str(getattr(current_room, "id", "")),
                "name": str(getattr(current_room, "name", "")),
                "description": str(getattr(current_room, "description", "")),
                "is_cleared": bool(getattr(current_room, "is_cleared", False)),
            }
            connected_rooms = []
            for room_id in list(getattr(current_room, "connections", []) or []):
                room_id_str = str(room_id)
                room = rooms_by_id.get(room_id_str)
                connected_rooms.append(
                    {
                        "id": room_id_str,
                        "name": str(getattr(room, "name", room_id_str)) if room is not None else room_id_str,
                    }
                )
            summary["connected_rooms"] = connected_rooms

    if state_value == GameState.ENCOUNTER.value:
        encounter = getattr(session, "encounter", None)
        if encounter is not None:
            summary["turn_order"] = list(getattr(encounter, "turn_order", []))
            summary["current_turn_index"] = int(getattr(encounter, "current_turn_index", 0))

            turn_order = list(getattr(encounter, "turn_order", []))
            current_turn_index = int(getattr(encounter, "current_turn_index", 0))
            current_actor_instance_id = ""
            if 0 <= current_turn_index < len(turn_order):
                current_actor_instance_id = str(turn_order[current_turn_index])
            summary["current_actor_instance_id"] = current_actor_instance_id

            actor_lookup: Dict[str, Any] = {}
            for player in list(getattr(session, "party", []) or []):
                instance_id = str(getattr(player, "player_instance_id", ""))
                if not instance_id:
                    continue
                actor_lookup[instance_id] = player

            current_encounter = getattr(encounter, "current_encounter", None)
            for enemy in list(getattr(current_encounter, "enemies", []) or []):
                instance_id = str(getattr(enemy, "enemy_instance_id", ""))
                if not instance_id:
                    continue
                actor_lookup[instance_id] = enemy

            current_actor = actor_lookup.get(current_actor_instance_id)
            summary["current_actor_name"] = str(getattr(current_actor, "name", current_actor_instance_id))

            def _attack_payload(attack: Any) -> Dict[str, Any]:
                return {
                    "id": str(getattr(attack, "id", "")),
                    "name": str(getattr(attack, "name", "")),
                    "target_type": str(getattr(getattr(attack, "target_type", None), "value", "")),
                }

            def _spell_payload(spell: Any) -> Dict[str, Any]:
                return {
                    "id": str(getattr(spell, "id", "")),
                    "name": str(getattr(spell, "name", "")),
                    "slot_cost": int(getattr(spell, "slot_cost", 0)),
                    "target_type": str(getattr(getattr(spell, "target_type", None), "value", "")),
                }

            if current_actor is not None:
                summary["available_attacks"] = [
                    _attack_payload(attack) for attack in list(getattr(current_actor, "merged_attacks", []) or [])
                ]
                summary["available_spells"] = [
                    _spell_payload(spell) for spell in list(getattr(current_actor, "merged_spells", []) or [])
                ]
            else:
                summary["available_attacks"] = []
                summary["available_spells"] = []

            actor_roster = []
            for actor_id, actor in actor_lookup.items():
                actor_roster.append(
                    {
                        "instance_id": actor_id,
                        "name": str(getattr(actor, "name", actor_id)),
                        "description": str(getattr(actor, "description", "")),
                        "hp": int(getattr(actor, "hp", 0)),
                        "max_hp": int(getattr(actor, "max_hp", 0)),
                    }
                )
            summary["actor_roster"] = actor_roster

            summary["entity_lookup"] = {
                actor["instance_id"]: {
                    "name": actor["name"],
                    "description": actor["description"],
                    "role": "player" if str(actor["instance_id"]).startswith("player_") else "enemy",
                }
                for actor in actor_roster
            }

    return summary
