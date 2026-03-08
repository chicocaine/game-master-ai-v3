from enum import Enum

class ActionType(Enum):
    ABANDON = "abandon"
    QUERY = "query"
    CONVERSE = "converse"

    MOVE = "move"
    REST = "rest"

    ATTACK = "attack"
    CAST_SPELL = "cast_spell"
    END_TURN = "end_turn" 

    START = "start"
    CREATE_PLAYER = "create_player"
    REMOVE_PLAYER = "remove_player"
    EDIT_PLAYER = "edit_player"
    CHOOSE_DUNGEON = "choose_dungeon"

    FINISH = "finish"

class EventType(Enum):
    GAME_STARTED = "game_started"
    GAME_FINISHED = "game_finished"
    GAME_STATE_CHANGED = "game_state_changed"
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    TURN_SKIPPED = "turn_skipped"

    NARRATION = "narration"
    QUERY = "query"
    CONVERSE = "query"
    SYSTEM_MESSAGE = "system_message"
    PLAYER_MESSAGE = "player_message"
    ERROR = "error"

    ACTION_SUBMITTED = "action_submitted"
    ACTION_VALIDATED = "action_validated"
    ACTION_REJECTED = "action_rejected"
    ACTION_RESOLVED = "action_resolved"

    PLAYER_CREATED = "player_created"
    PLAYER_REMOVED = "player_removed"
    PLAYER_EDITED = "player_edited"
    DUNGEON_CHOSEN = "dungeon_chosen"

    ROOM_ENTERED = "room_entered"
    ROOM_EXPLORED = "room_explored"
    ROOM_CLEARED = "room_cleared"
    MOVEMENT_RESOLVED = "movement_resolved"
    REST_STARTED = "rest_started"
    REST_COMPLETED = "rest_completed"

    ENCOUNTER_STARTED = "encounter_started"
    ENCOUNTER_ENDED = "encounter_ended"
    DICE_ROLLED = "dice_rolled"
    INITIATIVE_ROLLED = "initiative_rolled"
    ATTACK_DECLARED = "attack_declared"
    ATTACK_HIT = "attack_hit"
    ATTACK_MISSED = "attack_missed"
    DAMAGE_APPLIED = "damage_applied"
    SPELL_CAST = "spell_cast"
    HEALING_APPLIED = "healing_applied"
    STATUS_EFFECT_APPLIED = "status_effect_applied"
    STATUS_EFFECT_REMOVED = "status_effect_removed"
    STATUS_EFFECT_TICKED = "status_effect_ticked"
    DEATH = "death"
    REVIVE = "revive"

    HP_UPDATED = "hp_updated"
    SPELL_COUNT_UPDATED = "spell_count_updated"
    AC_UPDATED = "ac_updated"
    STATS_UPDATED = "stats_updated"
    REWARD_GRANTED = "reward_granted"
    PROGRESSION_UPDATED = "progression_updated"