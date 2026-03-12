from typing import Any, Dict, List

from game.core.enums import EventType


_EVENT_CATEGORIES: Dict[str, str] = {
    EventType.GAME_STARTED.value: "transition",
    EventType.GAME_FINISHED.value: "transition",
    EventType.GAME_STATE_CHANGED.value: "transition",
    EventType.TURN_STARTED.value: "combat",
    EventType.TURN_ENDED.value: "combat",
    EventType.TURN_SKIPPED.value: "combat",
    EventType.NARRATION.value: "system",
    EventType.CONVERSE.value: "converse",
    EventType.SYSTEM_MESSAGE.value: "system",
    EventType.PLAYER_MESSAGE.value: "converse",
    EventType.ERROR.value: "system",
    EventType.ACTION_SUBMITTED.value: "system",
    EventType.ACTION_VALIDATED.value: "system",
    EventType.ACTION_REJECTED.value: "system",
    EventType.ACTION_RESOLVED.value: "system",
    EventType.PLAYER_CREATED.value: "transition",
    EventType.PLAYER_REMOVED.value: "transition",
    EventType.PLAYER_EDITED.value: "transition",
    EventType.DUNGEON_CHOSEN.value: "transition",
    EventType.ROOM_ENTERED.value: "transition",
    EventType.ROOM_EXITED.value: "transition",
    EventType.ROOM_EXPLORED.value: "transition",
    EventType.ROOM_CLEARED.value: "transition",
    EventType.MOVEMENT_RESOLVED.value: "transition",
    EventType.REST_STARTED.value: "recovery",
    EventType.REST_COMPLETED.value: "recovery",
    EventType.ENCOUNTER_STARTED.value: "transition",
    EventType.ENCOUNTER_ENDED.value: "transition",
    EventType.DICE_ROLLED.value: "combat",
    EventType.DICE_RESULT.value: "combat",
    EventType.INITIATIVE_ROLLED.value: "combat",
    EventType.INITIATIVE_RESULT.value: "combat",
    EventType.DC_SAVE_THROW_ROLLED.value: "combat",
    EventType.ATTACK_DECLARED.value: "combat",
    EventType.ATTACK_HIT.value: "combat",
    EventType.ATTACK_MISSED.value: "combat",
    EventType.DAMAGE_APPLIED.value: "combat",
    EventType.SPELL_CAST.value: "combat",
    EventType.DAMAGE_INEFFECTIVE.value: "combat",
    EventType.DAMAGE_EFFECTIVE.value: "combat",
    EventType.DAMAGE_IMMUNE.value: "combat",
    EventType.CC_IMMUNE.value: "combat",
    EventType.HEALING_APPLIED.value: "recovery",
    EventType.STATUS_EFFECT_APPLIED.value: "combat",
    EventType.STATUS_EFFECT_REMOVED.value: "recovery",
    EventType.STATUS_EFFECT_TICKED.value: "combat",
    EventType.DEATH.value: "combat",
    EventType.REVIVE.value: "recovery",
    EventType.HP_UPDATED.value: "system",
    EventType.SPELL_COUNT_UPDATED.value: "system",
    EventType.AC_UPDATED.value: "system",
    EventType.STATS_UPDATED.value: "system",
    EventType.REWARD_GRANTED.value: "transition",
    EventType.PROGRESSION_UPDATED.value: "transition",
}


_EVENT_INTENSITY: Dict[str, int] = {
    EventType.GAME_FINISHED.value: 3,
    EventType.DEATH.value: 3,
    EventType.REVIVE.value: 3,
    EventType.ENCOUNTER_STARTED.value: 2,
    EventType.ENCOUNTER_ENDED.value: 2,
    EventType.INITIATIVE_RESULT.value: 2,
    EventType.ATTACK_HIT.value: 2,
    EventType.SPELL_CAST.value: 2,
    EventType.DAMAGE_EFFECTIVE.value: 2,
    EventType.DAMAGE_IMMUNE.value: 2,
    EventType.CC_IMMUNE.value: 2,
    EventType.DAMAGE_APPLIED.value: 1,
    EventType.ATTACK_MISSED.value: 1,
    EventType.ATTACK_DECLARED.value: 1,
    EventType.INITIATIVE_ROLLED.value: 1,
    EventType.DICE_ROLLED.value: 1,
    EventType.DICE_RESULT.value: 1,
    EventType.DC_SAVE_THROW_ROLLED.value: 1,
    EventType.ROOM_ENTERED.value: 1,
    EventType.ROOM_EXITED.value: 1,
    EventType.ROOM_EXPLORED.value: 1,
    EventType.MOVEMENT_RESOLVED.value: 1,
    EventType.HEALING_APPLIED.value: 1,
    EventType.STATUS_EFFECT_APPLIED.value: 1,
    EventType.STATUS_EFFECT_REMOVED.value: 1,
    EventType.STATUS_EFFECT_TICKED.value: 1,
    EventType.REWARD_GRANTED.value: 1,
}


def _event_type(event: Dict[str, Any]) -> str:
    return str(event.get("type", "")).strip()


def _category_for_event(event: Dict[str, Any]) -> str:
    event_type = _event_type(event)
    return _EVENT_CATEGORIES.get(event_type, "system")


def _intensity_for_event(event: Dict[str, Any]) -> int:
    event_type = _event_type(event)
    return int(_EVENT_INTENSITY.get(event_type, 0))


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