from typing import Any, Dict, List

from game.core.enums import EventType


_COMBAT_EVENTS = {
    EventType.ATTACK_DECLARED.value,
    EventType.ATTACK_HIT.value,
    EventType.ATTACK_MISSED.value,
    EventType.DAMAGE_APPLIED.value,
    EventType.SPELL_CAST.value,
    EventType.DEATH.value,
    EventType.REVIVE.value,
}

_TRANSITION_EVENTS = {
    EventType.GAME_STARTED.value,
    EventType.ROOM_EXITED.value,
    EventType.ROOM_ENTERED.value,
    EventType.MOVEMENT_RESOLVED.value,
    EventType.ENCOUNTER_STARTED.value,
    EventType.ENCOUNTER_ENDED.value,
    EventType.GAME_STATE_CHANGED.value,
}

_RECOVERY_EVENTS = {
    EventType.REST_STARTED.value,
    EventType.REST_COMPLETED.value,
    EventType.HEALING_APPLIED.value,
    EventType.STATUS_EFFECT_REMOVED.value,
}


def _event_type(event: Dict[str, Any]) -> str:
    return str(event.get("type", "")).strip()


def _category_for_event(event: Dict[str, Any]) -> str:
    event_type = _event_type(event)
    if event_type in _COMBAT_EVENTS:
        return "combat"
    if event_type in _TRANSITION_EVENTS:
        return "transition"
    if event_type in _RECOVERY_EVENTS:
        return "recovery"
    if event_type == EventType.CONVERSE.value:
        return "converse"
    return "system"


def _intensity_for_event(event: Dict[str, Any]) -> int:
    event_type = _event_type(event)
    if event_type in {EventType.DEATH.value, EventType.REVIVE.value}:
        return 3
    if event_type in {EventType.ATTACK_HIT.value, EventType.SPELL_CAST.value, EventType.ENCOUNTER_STARTED.value}:
        return 2
    if event_type in {
        EventType.DAMAGE_APPLIED.value,
        EventType.ATTACK_MISSED.value,
        EventType.ROOM_ENTERED.value,
        EventType.ROOM_EXITED.value,
        EventType.MOVEMENT_RESOLVED.value,
    }:
        return 1
    return 0


def build_event_beats(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group adjacent events by narrative category into deterministic beats."""
    beats: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    for event in events:
        category = _category_for_event(event)
        intensity = _intensity_for_event(event)

        if current is None or current["category"] != category:
            current = {
                "beat_id": f"beat_{len(beats) + 1}",
                "category": category,
                "intensity": intensity,
                "events": [dict(event)],
            }
            beats.append(current)
            continue

        current["events"].append(dict(event))
        current["intensity"] = max(int(current["intensity"]), intensity)

    return beats


def target_sentences_for_beats(beats: List[Dict[str, Any]], max_sentences: int = 5) -> int:
    if max_sentences <= 0:
        return 1
    if not beats:
        return 1

    max_intensity = max(int(beat.get("intensity", 0)) for beat in beats)
    target = len(beats)
    if max_intensity >= 3:
        target += 1
    return max(1, min(max_sentences, target))