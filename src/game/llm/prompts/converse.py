from typing import Any, Dict, List


def system_instructions() -> str:
    return (
        "You are the game master speaking directly to players. "
        "Tone is dynamic by context; witty, playful, or snarky replies are allowed when they still help the player. "
        "Use parser_reasoning and parser_metadata to explain invalid, blocked, or ambiguous intent outcomes when present. "
        "If parser_metadata.fallback_reason is 'pregame_setup_action', do not pretend the setup action already happened. "
        "Instead, briefly acknowledge the request, confirm the exact setup details that will be used, or ask the next clarifying question needed to complete setup. "
        "For those setup replies, prefer concise guidance over roleplay flourishes. "
        "Return one JSON object containing a helpful in-world reply. "
        "Include a non-empty reasoning field that explains why your reply resolves the player's current input. "
        "Do not include markdown."
    )


def build_user_payload(
    player_message: str,
    state_summary: Dict[str, Any],
    parser_reasoning: str = "",
    parser_metadata: Dict[str, Any] | None = None,
    context_envelope: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    metadata = dict(parser_metadata or {})
    reply_policy: Dict[str, Any] = {"mode": "default"}
    if metadata.get("fallback_reason") == "pregame_setup_action":
        reply_policy = {
            "mode": "setup_guidance",
            "requested_action_type": str(metadata.get("requested_action_type", "")),
            "requirements": [
                "Do not claim the setup action is already applied.",
                "Acknowledge the request and either confirm the interpreted setup details or ask one concise follow-up question.",
                "Keep the reply actionable and brief.",
            ],
        }

    payload = {
        "domain": "converse",
        "player_message": player_message,
        "state_summary": dict(state_summary),
        "parser_reasoning": str(parser_reasoning or ""),
        "parser_metadata": metadata,
        "reply_policy": reply_policy,
    }
    if context_envelope is not None:
        payload["context_envelope"] = dict(context_envelope)
    return payload


def build_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["reply", "reasoning"],
        "additionalProperties": False,
        "properties": {
            "reply": {"type": "string"},
            "reasoning": {"type": "string"},
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
            "output": {
                "reply": "You notice scuffed stone leading toward a cracked archway.",
                "reasoning": "The player asked a world-query, so the reply should provide an actionable environmental clue.",
                "tone": "mysterious",
            },
        },
        {
            "input": "Add Elara, a human mage with a sage staff.",
            "output": {
                "reply": "I can set that up. I have Elara as a human mage with a sage staff. If that matches your intent, I'll use those details for the party setup.",
                "reasoning": "This is a pregame setup request routed through converse, so the reply should confirm the interpreted setup details without claiming the player was already created.",
                "tone": "helpful",
                "metadata": {"response_class": "setup_guidance"},
            },
        },
    ]
