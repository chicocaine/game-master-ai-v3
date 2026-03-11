from typing import Any, Dict, List

from game.core.enums import ActionType

from game.llm.prompts.base import base_system_instructions, build_action_response_schema


_ALLOWED_ENEMY_ACTIONS = [
    ActionType.ATTACK.value,
    ActionType.CAST_SPELL.value,
    ActionType.END_TURN.value,
]


def system_instructions() -> str:
    return base_system_instructions("enemy_ai", _ALLOWED_ENEMY_ACTIONS)


def build_user_payload(
    actor_instance_id: str,
    enemy_persona: str,
    combat_summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "domain": "enemy_ai",
        "actor_instance_id": actor_instance_id,
        "enemy_persona": enemy_persona,
        "allowed_actions": list(_ALLOWED_ENEMY_ACTIONS),
        "combat_summary": dict(combat_summary),
    }


def build_response_schema() -> Dict[str, Any]:
    return build_action_response_schema(_ALLOWED_ENEMY_ACTIONS)


def few_shot_examples() -> List[Dict[str, Any]]:
    return [
        {
            "input": "Focus low-hp target with basic attack",
            "output": {
                "type": "attack",
                "actor_instance_id": "enemy_1",
                "parameters": {
                    "attack_id": "claw",
                    "target_instance_ids": ["player_1"],
                },
            },
        },
        {
            "input": "No good tactical move available",
            "output": {
                "type": "end_turn",
                "actor_instance_id": "enemy_1",
                "parameters": {},
            },
        },
    ]
