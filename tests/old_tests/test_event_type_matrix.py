from game.core.enums import EventType


# Event types actively emitted by current gameplay/state handlers.
EMITTED_EVENT_TYPES = {
    EventType.GAME_STARTED.value,
    EventType.GAME_FINISHED.value,
    EventType.GAME_STATE_CHANGED.value,
    EventType.TURN_STARTED.value,
    EventType.TURN_ENDED.value,
    EventType.TURN_SKIPPED.value,
    EventType.CONVERSE.value,
    EventType.ACTION_SUBMITTED.value,
    EventType.ACTION_VALIDATED.value,
    EventType.ACTION_REJECTED.value,
    EventType.ACTION_RESOLVED.value,
    EventType.PLAYER_CREATED.value,
    EventType.PLAYER_REMOVED.value,
    EventType.PLAYER_EDITED.value,
    EventType.DUNGEON_CHOSEN.value,
    EventType.ROOM_ENTERED.value,
    EventType.ROOM_EXITED.value,
    EventType.ROOM_EXPLORED.value,
    EventType.MOVEMENT_RESOLVED.value,
    EventType.REST_STARTED.value,
    EventType.REST_COMPLETED.value,
    EventType.ENCOUNTER_STARTED.value,
    EventType.ENCOUNTER_ENDED.value,
    EventType.INITIATIVE_ROLLED.value,
    EventType.ATTACK_DECLARED.value,
    EventType.ATTACK_HIT.value,
    EventType.ATTACK_MISSED.value,
    EventType.DAMAGE_APPLIED.value,
    EventType.SPELL_CAST.value,
    EventType.HEALING_APPLIED.value,
    EventType.STATUS_EFFECT_APPLIED.value,
    EventType.STATUS_EFFECT_REMOVED.value,
    EventType.STATUS_EFFECT_TICKED.value,
    EventType.DEATH.value,
    EventType.REWARD_GRANTED.value,
}

# Event types defined in enum but intentionally reserved or not yet emitted in current flow.
RESERVED_EVENT_TYPES = {
    EventType.NARRATION.value,
    EventType.SYSTEM_MESSAGE.value,
    EventType.PLAYER_MESSAGE.value,
    EventType.ERROR.value,
    EventType.ROOM_CLEARED.value,
    EventType.DICE_ROLLED.value,
    EventType.DC_SAVE_THROW_ROLLED.value,
    EventType.DAMAGE_INEFFECTIVE.value,
    EventType.DAMAGE_EFFECTIVE.value,
    EventType.DAMAGE_IMMUNE.value,
    EventType.CC_IMMUNE.value,
    EventType.REVIVE.value,
    EventType.HP_UPDATED.value,
    EventType.SPELL_COUNT_UPDATED.value,
    EventType.AC_UPDATED.value,
    EventType.STATS_UPDATED.value,
    EventType.PROGRESSION_UPDATED.value,
}

# Event types with explicit user-facing rendering in CLI renderer.
RENDERED_EVENT_TYPES = {
    EventType.GAME_STARTED.value,
    EventType.CONVERSE.value,
    EventType.GAME_STATE_CHANGED.value,
    EventType.PLAYER_CREATED.value,
    EventType.PLAYER_REMOVED.value,
    EventType.PLAYER_EDITED.value,
    EventType.DUNGEON_CHOSEN.value,
    EventType.MOVEMENT_RESOLVED.value,
    EventType.ROOM_EXITED.value,
    EventType.ROOM_ENTERED.value,
    EventType.ROOM_EXPLORED.value,
    EventType.REST_STARTED.value,
    EventType.REST_COMPLETED.value,
    EventType.ENCOUNTER_STARTED.value,
    EventType.INITIATIVE_ROLLED.value,
    EventType.TURN_STARTED.value,
    EventType.TURN_ENDED.value,
    EventType.TURN_SKIPPED.value,
    EventType.ATTACK_HIT.value,
    EventType.ATTACK_MISSED.value,
    EventType.DAMAGE_APPLIED.value,
    EventType.HEALING_APPLIED.value,
    EventType.REWARD_GRANTED.value,
    EventType.ENCOUNTER_ENDED.value,
}


def test_event_type_matrix_has_complete_primary_classification():
    all_event_types = {event_type.value for event_type in EventType}
    assert EMITTED_EVENT_TYPES.isdisjoint(RESERVED_EVENT_TYPES)
    assert EMITTED_EVENT_TYPES | RESERVED_EVENT_TYPES == all_event_types


def test_event_type_matrix_rendering_entries_are_known_event_types():
    all_event_types = {event_type.value for event_type in EventType}
    assert RENDERED_EVENT_TYPES.issubset(all_event_types)
