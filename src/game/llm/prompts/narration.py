from typing import Any, Dict, List


def system_instructions() -> str:
    return (
        "You are a dungeon master narration generator. "
        "Return one JSON object with atmospheric but concise narration for the provided events. "
        "Do not include markdown."
    )


def build_user_payload(events: List[Dict[str, Any]], state_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "domain": "narration",
        "events": list(events),
        "state_summary": dict(state_summary),
    }


def build_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["text"],
        "additionalProperties": False,
        "properties": {
            "text": {"type": "string"},
            "style": {"type": "string"},
            "focus_event_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "metadata": {"type": "object"},
        },
    }


def few_shot_examples() -> List[Dict[str, Any]]:
    return [
        {
            "input": {
                "events": [{"type": "room_entered", "room_id": "room_2"}],
            },
            "output": {
                "text": "The party steps into room_2, where stale air and distant echoes signal danger ahead.",
                "style": "atmospheric",
            },
        }
    ]
