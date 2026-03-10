from typing import Any, Dict, List


def system_instructions() -> str:
    return (
        "You are the game master speaking directly to players. "
        "Return one JSON object containing a helpful in-world reply. "
        "Do not include markdown."
    )


def build_user_payload(player_message: str, state_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "domain": "converse",
        "player_message": player_message,
        "state_summary": dict(state_summary),
    }


def build_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["reply"],
        "additionalProperties": False,
        "properties": {
            "reply": {"type": "string"},
            "tone": {"type": "string"},
            "metadata": {"type": "object"},
        },
    }


def few_shot_examples() -> List[Dict[str, Any]]:
    return [
        {
            "input": "Any clues in this room?",
            "output": {"reply": "You notice scuffed stone leading toward a cracked archway.", "tone": "mysterious"},
        }
    ]
