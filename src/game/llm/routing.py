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
    summary: Dict[str, Any] = {
        "state": getattr(getattr(session, "state", None), "value", ""),
        "party_size": len(getattr(session, "party", [])),
        "points": int(getattr(session, "points", 0)),
    }

    dungeon = getattr(session, "dungeon", None)
    if dungeon is not None:
        summary["dungeon_id"] = str(getattr(dungeon, "id", ""))

    exploration = getattr(session, "exploration", None)
    current_room = getattr(exploration, "current_room", None) if exploration is not None else None
    if current_room is not None:
        summary["current_room_id"] = str(getattr(current_room, "id", ""))
        summary["current_room_cleared"] = bool(getattr(current_room, "is_cleared", False))

    encounter = getattr(session, "encounter", None)
    if encounter is not None:
        summary["turn_order"] = list(getattr(encounter, "turn_order", []))
        summary["current_turn_index"] = int(getattr(encounter, "current_turn_index", 0))

    return summary
