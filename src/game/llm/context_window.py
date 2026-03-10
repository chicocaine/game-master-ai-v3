import json
import math
from typing import Any, Callable, Dict, Iterable, List


def estimate_tokens_from_text(text: str) -> int:
    """Estimate tokens using a deterministic 4-chars-per-token heuristic."""
    if not text:
        return 0
    return max(1, int(math.ceil(len(text) / 4)))


def estimate_tokens(value: Any) -> int:
    return estimate_tokens_from_text(json.dumps(value, sort_keys=True, ensure_ascii=True))


def truncate_text_to_token_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def fit_dict_to_token_budget(
    payload: Dict[str, Any],
    max_tokens: int,
    priority_keys: Iterable[str] | None = None,
) -> Dict[str, Any]:
    """Trim dict payload deterministically by dropping non-priority keys until budget fits."""
    data = dict(payload)
    if estimate_tokens(data) <= max_tokens:
        return data

    priorities = list(priority_keys or [])
    protected = set(priorities)

    removable_keys = sorted([key for key in data.keys() if key not in protected])
    for key in removable_keys:
        if estimate_tokens(data) <= max_tokens:
            break
        data.pop(key, None)

    if estimate_tokens(data) <= max_tokens:
        return data

    # Last resort: truncate any oversized string values, keeping deterministic key order.
    for key in sorted(data.keys()):
        if estimate_tokens(data) <= max_tokens:
            break
        value = data.get(key)
        if isinstance(value, str):
            target_tokens = max(1, max_tokens // max(1, len(data)))
            data[key] = truncate_text_to_token_budget(value, target_tokens)

    return data


def build_recent_window(
    items: List[Any],
    max_items: int,
    max_tokens: int,
    serializer: Callable[[Any], str] | None = None,
) -> List[Any]:
    """Keep latest items that fit item and token limits while preserving chronological order."""
    if max_items <= 0 or max_tokens <= 0 or not items:
        return []

    serialize = serializer or (lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True))

    selected_reversed: List[Any] = []
    used_tokens = 0

    for item in reversed(items):
        if len(selected_reversed) >= max_items:
            break
        item_tokens = estimate_tokens_from_text(serialize(item))
        if item_tokens > max_tokens:
            continue
        if used_tokens + item_tokens > max_tokens:
            continue
        selected_reversed.append(item)
        used_tokens += item_tokens

    return list(reversed(selected_reversed))
