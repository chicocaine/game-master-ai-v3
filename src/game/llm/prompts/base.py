from typing import Any, Dict, List

from game.core.enums import ActionType
from game.enums import GameState


_ALLOWED_BY_STATE: dict[GameState, list[ActionType]] = {
    GameState.PREGAME: [
        ActionType.CREATE_PLAYER,
        ActionType.REMOVE_PLAYER,
        ActionType.EDIT_PLAYER,
        ActionType.CHOOSE_DUNGEON,
        ActionType.START,
        ActionType.CONVERSE,
    ],
    GameState.EXPLORATION: [
        ActionType.MOVE,
        ActionType.REST,
        ActionType.CONVERSE,
    ],
    GameState.ENCOUNTER: [
        ActionType.ATTACK,
        ActionType.CAST_SPELL,
        ActionType.END_TURN,
        ActionType.CONVERSE,
    ],
    GameState.POSTGAME: [
        ActionType.FINISH,
        ActionType.CONVERSE,
    ],
}


def allowed_action_types_for_state(state: GameState) -> list[ActionType]:
    return list(_ALLOWED_BY_STATE.get(state, [ActionType.CONVERSE]))


def allowed_action_values_for_state(state: GameState) -> list[str]:
    return [action_type.value for action_type in allowed_action_types_for_state(state)]


def build_action_response_schema(allowed_action_values: list[str]) -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["type", "parameters", "reasoning"],
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": list(allowed_action_values)},
            "actor_instance_id": {"type": "string"},
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    # converse
                    "message": {"type": "string"},
                    # create_player / edit_player
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "race": {"type": "string", "description": "race_id — must be an ID from available_races (e.g. race_human), never a display name"},
                    "archetype": {"type": "string", "description": "archetype_id — must be an ID from available_archetypes (e.g. arch_knight), never a display name"},
                    "weapons": {"type": "array", "items": {"type": "string", "description": "weapon_id from available_weapons (e.g. wpn_iron_sword), never a display name"}},
                    # remove_player / edit_player
                    "player_instance_id": {"type": "string"},
                    # choose_dungeon
                    "dungeon": {"type": "string", "description": "dungeon_id — must be an ID from available_dungeons (e.g. dng_ember_ruins), never a display name"},
                    # move
                    "destination_room_id": {"type": "string"},
                    # rest
                    "rest_type": {"type": "string"},
                    # attack
                    "attack_id": {"type": "string"},
                    # cast_spell
                    "spell_id": {"type": "string"},
                    # attack / cast_spell
                    "target_instance_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
            "reasoning": {"type": "string"},
            "metadata": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
    }


def build_common_user_payload(
    player_input: str,
    actor_instance_id: str,
    state: GameState,
    state_summary: Dict[str, Any],
    allowed_action_values: list[str],
    context_envelope: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = {
        "state": state.value,
        "actor_instance_id": actor_instance_id,
        "allowed_actions": list(allowed_action_values),
        "player_input": player_input,
        "state_summary": dict(state_summary),
    }
    if context_envelope is not None:
        payload["context_envelope"] = dict(context_envelope)
    return payload


def base_system_instructions(domain_name: str, allowed_action_values: list[str]) -> str:
    allowed_list = ", ".join(allowed_action_values)
    return (
        "You are a game-master intent parser for a tabletop-style RPG engine. "
        f"Domain: {domain_name}. "
        "Return exactly one action JSON object. "
        f"Allowed action types: {allowed_list}. "
        "Use player_input together with recent_conversation and context_envelope.past_context.timeline to interpret short confirmations "
        "(e.g. 'ok', 'okay sure', 'yes') in context. "
        "If recent context makes one concrete action unambiguous, emit that action with complete canonical IDs. "
        "Reasoning is mandatory and must explain why the selected action is valid for the provided input and state. "
        "Before responding, verify all required parameters for the chosen action are complete and non-empty. "
        "If required parameters are missing, output type='converse' and keep parameters.message equal to the player's original input verbatim. "
        "Never generate assistant replies inside parameters.message; it is for carrying original player text only. "
        "For create_player and edit_player, 'race', 'archetype', and every 'weapons' item must be the exact ID from the available roster "
        "(e.g. use 'race_human' not 'Human', 'arch_knight' not 'Knight', 'wpn_iron_sword' not 'Iron Sword'). "
        "For choose_dungeon, 'dungeon' must be the exact ID from available_dungeons (e.g. 'dng_ember_ruins' not 'Ember Ruins'). "
        "Do not include markdown, code fences, or prose outside the JSON object."
        "You can infer and reason out the required action parameters based on the context as long as it is accurate."
    )


def build_common_few_shot_examples() -> List[Dict[str, Any]]:
    return [
        {
            "input": "Can we talk about the plan first?",
            "output": {
                "type": "converse",
                "parameters": {"message": "Can we talk about the plan first?"},
                "reasoning": "The player asked an open-ended conversation question, so converse is the correct action.",
            },
        }
    ]
