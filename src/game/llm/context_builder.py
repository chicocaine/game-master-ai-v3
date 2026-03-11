from typing import Any, Dict, Iterable, List, Mapping

from game.llm.context_window import build_recent_window
from game.llm.json_parse import validate_context_envelope


DEFAULT_IDENTITY_NAME = "game-master-ai"
DEFAULT_IDENTITY_ALIASES = ["dm", "game master"]


def _prune_current_context(current_context: Mapping[str, Any]) -> Dict[str, Any]:
    context = {str(key): value for key, value in dict(current_context).items()}
    state = str(context.get("state", "")).strip().lower()

    # Remove obviously empty values from the envelope to keep context compact.
    compact = {key: value for key, value in context.items() if value not in (None, "", [], {})}

    if state == "pregame":
        compact.pop("current_room_id", None)
        compact.pop("current_room_cleared", None)
        compact.pop("turn_order", None)
        compact.pop("current_turn_index", None)
    elif state == "exploration":
        compact.pop("turn_order", None)
        compact.pop("current_turn_index", None)
    elif state == "postgame":
        compact.pop("current_room_id", None)
        compact.pop("current_room_cleared", None)
        compact.pop("turn_order", None)
        compact.pop("current_turn_index", None)

    return compact


def build_past_timeline(
    timeline_entries: Iterable[Mapping[str, Any]],
    max_items: int,
    max_tokens: int,
) -> List[Dict[str, Any]]:
    items = [dict(entry) for entry in timeline_entries]
    return build_recent_window(items, max_items=max_items, max_tokens=max_tokens)


def build_context_envelope(
    *,
    current_context: Mapping[str, Any],
    allowed_actions: Iterable[str],
    actor_context: Mapping[str, Any],
    timeline_entries: Iterable[Mapping[str, Any]],
    identity_name: str = DEFAULT_IDENTITY_NAME,
    identity_aliases: Iterable[str] = DEFAULT_IDENTITY_ALIASES,
    max_timeline_items: int = 12,
    max_timeline_tokens: int = 256,
) -> Dict[str, Any]:
    envelope = {
        "identity": {
            "name": str(identity_name),
            "aliases": [str(alias) for alias in identity_aliases],
        },
        "past_context": {
            "timeline": build_past_timeline(
                timeline_entries=timeline_entries,
                max_items=max_timeline_items,
                max_tokens=max_timeline_tokens,
            )
        },
        "current_context": _prune_current_context(current_context),
        "allowed_actions": [str(action) for action in allowed_actions],
        "actor_context": dict(actor_context),
    }
    return validate_context_envelope(envelope)