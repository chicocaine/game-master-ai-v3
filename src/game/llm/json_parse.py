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
        "style": style,
        "focus_event_ids": focus_event_ids,
        "metadata": metadata,
    }
