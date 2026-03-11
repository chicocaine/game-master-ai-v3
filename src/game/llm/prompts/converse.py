from typing import Any, Dict, List


def system_instructions() -> str:
    return (
        "You are the game master speaking directly to players. "
        "Tone is dynamic by context; witty, playful, or snarky replies are allowed when they still help the player. "
        "Return one JSON object containing a helpful in-world reply. "
        "Do not include markdown."
    )


def build_user_payload(
    player_message: str,
    state_summary: Dict[str, Any],
    context_envelope: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = {
        "domain": "converse",
        "player_message": player_message,
        "state_summary": dict(state_summary),
    }
    if context_envelope is not None:
        payload["context_envelope"] = dict(context_envelope)
    return payload


def build_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["reply"],
        "additionalProperties": False,
        "properties": {
            "reply": {"type": "string"},
            "tone": {"type": "string"},
            "metadata": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
    }


def few_shot_examples() -> List[Dict[str, Any]]:
    return [
        {
            "input": "Any clues in this room?",
            "output": {"reply": "You notice scuffed stone leading toward a cracked archway.", "tone": "mysterious"},
        }
    ]
