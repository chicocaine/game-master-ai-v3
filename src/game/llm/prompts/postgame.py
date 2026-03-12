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
    allowed = allowed_action_values_for_state(GameState.POSTGAME)
    return base_system_instructions("postgame", allowed)


def build_user_payload(
    player_input: str,
    actor_instance_id: str,
    state_summary: Dict[str, Any],
    context_envelope: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    allowed = allowed_action_values_for_state(GameState.POSTGAME)
    payload = build_common_user_payload(
        player_input=player_input,
        actor_instance_id=actor_instance_id,
        state=GameState.POSTGAME,
        state_summary=state_summary,
        allowed_action_values=allowed,
        context_envelope=context_envelope,
    )
    payload["goal"] = "Wrap up the session and finish cleanly."
    return payload


def build_response_schema() -> Dict[str, Any]:
    return build_action_response_schema(allowed_action_values_for_state(GameState.POSTGAME))


def few_shot_examples() -> List[Dict[str, Any]]:
    examples = build_common_few_shot_examples()
    examples.append(
        {
            "input": "Finish the run.",
            "output": {
                "type": "finish",
                "parameters": {},
                "reasoning": "The player requested to end the session, which maps directly to finish.",
            },
        }
    )
    return examples
