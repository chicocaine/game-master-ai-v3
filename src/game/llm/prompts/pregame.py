from typing import Any, Dict, List

from game.enums import GameState
from game.llm.prompts.base import (
    allowed_action_values_for_state,
    base_system_instructions,
    build_action_response_schema,
    build_common_few_shot_examples,
    build_common_user_payload,
)


def system_instructions() -> str:
    allowed = allowed_action_values_for_state(GameState.PREGAME)
    return base_system_instructions("pregame", allowed)


def build_user_payload(
    player_input: str,
    actor_instance_id: str,
    state_summary: Dict[str, Any],
    context_envelope: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    allowed = allowed_action_values_for_state(GameState.PREGAME)
    payload = build_common_user_payload(
        player_input=player_input,
        actor_instance_id=actor_instance_id,
        state=GameState.PREGAME,
        state_summary=state_summary,
        allowed_action_values=allowed,
        context_envelope=context_envelope,
    )
    payload["goal"] = "Form party, choose dungeon, and start game when ready."
    return payload


def build_response_schema() -> Dict[str, Any]:
    return build_action_response_schema(allowed_action_values_for_state(GameState.PREGAME))


def few_shot_examples() -> List[Dict[str, Any]]:
    examples = build_common_few_shot_examples()
    examples.append(
        {
            "input": "Start the game now.",
            "output": {
                "type": "start",
                "parameters": {},
                "reasoning": "The player clearly requested game start and no additional parameters are required.",
            },
        }
    )
    examples.append(
        {
            "input": "I choose Ember Ruins as the dungeon.",
            "output": {
                "type": "choose_dungeon",
                "parameters": {"dungeon": "dng_ember_ruins"},
                "reasoning": "The player explicitly selected a dungeon; mapped display name 'Ember Ruins' to canonical dungeon_id 'dng_ember_ruins'.",
            },
        }
    )
    examples.append(
        {
            "input": "Add Elara, a human mage with a sage staff.",
            "output": {
                "type": "converse",
                "parameters": {"message": "Add Elara, a human mage with a sage staff."},
                "reasoning": "Pregame setup requests like character creation should route to converse so the game master can confirm and handle the setup conversationally.",
            },
        }
    )
    return examples
