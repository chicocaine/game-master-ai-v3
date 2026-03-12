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
        compact.pop("current_actor_instance_id", None)
        compact.pop("current_actor_name", None)
        compact.pop("available_attacks", None)
        compact.pop("available_spells", None)
        compact.pop("actor_roster", None)
        compact.pop("entity_lookup", None)
    elif state == "exploration":
        compact.pop("turn_order", None)
        compact.pop("current_turn_index", None)
        compact.pop("current_actor_instance_id", None)
        compact.pop("current_actor_name", None)
        compact.pop("available_attacks", None)
        compact.pop("available_spells", None)
        compact.pop("actor_roster", None)
        compact.pop("entity_lookup", None)
    elif state == "postgame":
        compact.pop("current_room_id", None)
        compact.pop("current_room_cleared", None)
        compact.pop("turn_order", None)
        compact.pop("current_turn_index", None)
        compact.pop("current_actor_instance_id", None)
        compact.pop("current_actor_name", None)
        compact.pop("available_attacks", None)
        compact.pop("available_spells", None)
        compact.pop("actor_roster", None)
        compact.pop("entity_lookup", None)

    return compact


def _annotate_timeline_entry(entry: Mapping[str, Any], entity_lookup: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    annotated = dict(entry)
    actor_id = str(annotated.get("actor_instance_id", "")).strip()
    target_id = str(annotated.get("target_instance_id", "")).strip()

    if actor_id and actor_id in entity_lookup:
        actor_payload = entity_lookup[actor_id]
        annotated["actor_name"] = str(actor_payload.get("name", actor_id))
    if target_id and target_id in entity_lookup:
        target_payload = entity_lookup[target_id]
        annotated["target_name"] = str(target_payload.get("name", target_id))

    return annotated


def build_past_timeline(
    timeline_entries: Iterable[Mapping[str, Any]],
    entity_lookup: Mapping[str, Mapping[str, Any]],
    max_items: int,
    max_tokens: int,
) -> List[Dict[str, Any]]:
    items = [_annotate_timeline_entry(entry, entity_lookup) for entry in timeline_entries]
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
    context = _prune_current_context(current_context)
    raw_lookup = context.get("entity_lookup", {})
    entity_lookup = raw_lookup if isinstance(raw_lookup, dict) else {}

    envelope = {
        "identity": {
            "name": str(identity_name),
            "aliases": [str(alias) for alias in identity_aliases],
        },
        "past_context": {
            "timeline": build_past_timeline(
                timeline_entries=timeline_entries,
                entity_lookup=entity_lookup,
                max_items=max_timeline_items,
                max_tokens=max_timeline_tokens,
            )
        },
        "current_context": context,
        "allowed_actions": [str(action) for action in allowed_actions],
        "actor_context": dict(actor_context),
    }
    return validate_context_envelope(envelope)