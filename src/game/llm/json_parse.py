import json
import re
from typing import Any, Mapping

from game.llm.errors import LlmResponseParseError, LlmSchemaValidationError


_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _extract_first_json_object(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        raise LlmResponseParseError("Model response is empty.")

    match = _CODE_BLOCK_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LlmResponseParseError("No JSON object found in model response.")
    return text[start : end + 1]


def parse_json_object(raw_text: str) -> dict[str, Any]:
    candidate = _extract_first_json_object(raw_text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LlmResponseParseError(f"Failed to parse JSON response: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise LlmResponseParseError("Expected a JSON object at top level.")
    return payload


def _require_non_empty_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str) or not value.strip():
        raise LlmSchemaValidationError(f"'{key}' must be a non-empty string.")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LlmSchemaValidationError(f"'{key}' must be a string when provided.")
    return value


def _optional_object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LlmSchemaValidationError(f"'{key}' must be an object when provided.")
    return dict(value)


def _require_object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise LlmSchemaValidationError(f"'{key}' must be an object.")
    return dict(value)


def _require_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise LlmSchemaValidationError(f"'{key}' must be a list.")

    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise LlmSchemaValidationError(f"'{key}' must contain non-empty strings.")
        items.append(item.strip())
    return items


def validate_action_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    action_type = _require_non_empty_string(payload, "type")
    actor_instance_id = _optional_string(payload, "actor_instance_id").strip()
    parameters = _optional_object(payload, "parameters")
    reasoning = _optional_string(payload, "reasoning").strip()
    metadata = _optional_object(payload, "metadata")

    return {
        "type": action_type,
        "actor_instance_id": actor_instance_id,
        "parameters": parameters,
        "reasoning": reasoning,
        "metadata": metadata,
    }


def validate_narration_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    text = _require_non_empty_string(payload, "text")
    reasoning = _require_non_empty_string(payload, "reasoning")
    style = _optional_string(payload, "style").strip()
    metadata = _optional_object(payload, "metadata")

    focus_event_ids_raw = payload.get("focus_event_ids", [])
    if focus_event_ids_raw is None:
        focus_event_ids: list[str] = []
    elif isinstance(focus_event_ids_raw, list):
        focus_event_ids = []
        for item in focus_event_ids_raw:
            if not isinstance(item, str) or not item.strip():
                raise LlmSchemaValidationError("'focus_event_ids' must contain non-empty strings.")
            focus_event_ids.append(item)
    else:
        raise LlmSchemaValidationError("'focus_event_ids' must be a list when provided.")

    return {
        "text": text,
        "reasoning": reasoning,
        "style": style,
        "focus_event_ids": focus_event_ids,
        "metadata": metadata,
    }


def validate_context_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    identity = _require_object(payload, "identity")
    past_context = _require_object(payload, "past_context")
    current_context = _require_object(payload, "current_context")
    allowed_actions = _require_string_list(payload, "allowed_actions")
    actor_context = _require_object(payload, "actor_context")

    identity_name = identity.get("name", "")
    if not isinstance(identity_name, str) or not identity_name.strip():
        raise LlmSchemaValidationError("'identity.name' must be a non-empty string.")

    aliases = identity.get("aliases", [])
    if aliases is None:
        aliases = []
    if not isinstance(aliases, list):
        raise LlmSchemaValidationError("'identity.aliases' must be a list.")
    normalized_aliases: list[str] = []
    for alias in aliases:
        if not isinstance(alias, str) or not alias.strip():
            raise LlmSchemaValidationError("'identity.aliases' must contain non-empty strings.")
        normalized_aliases.append(alias.strip())

    timeline = past_context.get("timeline", [])
    if timeline is None:
        timeline = []
    if not isinstance(timeline, list):
        raise LlmSchemaValidationError("'past_context.timeline' must be a list.")
    for entry in timeline:
        if not isinstance(entry, dict):
            raise LlmSchemaValidationError("'past_context.timeline' entries must be objects.")

    return {
        "identity": {
            "name": identity_name.strip(),
            "aliases": normalized_aliases,
        },
        "past_context": {
            **past_context,
            "timeline": [dict(entry) for entry in timeline],
        },
        "current_context": current_context,
        "allowed_actions": allowed_actions,
        "actor_context": actor_context,
    }
