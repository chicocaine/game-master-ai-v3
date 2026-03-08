from types import SimpleNamespace

from core.action import create_action
from core.enums import ActionType
from game.actors.enemy import create_enemy
from game.dungeons.dungeon import Encounter
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import (
    DifficultyType,
    GameState,
    WeaponDelivery,
    WeaponHandling,
    WeaponMagicType,
    WeaponProficiency,
    WeaponWeightClass,
)
from game.states.encounter import EncounterState
from game.states.pregame import PreGameState


def _race() -> Race:
    return Race(
        id="race_1",
        name="Race",
        description="",
        base_hp=10,
        base_AC=10,
        base_spell_slots=2,
    )


def _archetype() -> Archetype:
    return Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=2,
        AC_mod=1,
        spell_slot_mod=1,
        initiative_mod=0,
        weapon_constraints=WeaponConstraints(),
    )


def _weapon() -> Weapon:
    return Weapon(
        id="wpn_1",
        name="Weapon",
        description="",
        proficiency=WeaponProficiency.SIMPLE,
        handling=WeaponHandling.ONE_HANDED,
        weight_class=WeaponWeightClass.LIGHT,
        delivery=WeaponDelivery.MELEE,
        magic_type=WeaponMagicType.MUNDANE,
    )


def _session_with_party() -> SimpleNamespace:
    session = SimpleNamespace(
        party=[],
        state=GameState.EXPLORATION,
    )
    pregame = PreGameState()
    errors = pregame.handle_create_player(
        session,
        id="player_1",
        name="Player",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    assert errors == []
    return session


def _encounter() -> Encounter:
    enemy = create_enemy(
        id="enemy_1",
        name="Enemy",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
        enemy_instance_id="enemy_inst_1",
    )
    return Encounter(
        id="enc_1",
        name="Encounter",
        description="",
        difficulty=DifficultyType.EASY,
        cleared=False,
        clear_reward=10,
        enemies=[enemy],
    )


def test_start_and_advance_turn_placeholder_flow() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()

    errors = state.start_encounter(session, encounter)
    assert errors == []
    assert session.state is GameState.ENCOUNTER
    assert state.current_encounter is encounter
    assert state.turn_order == ["player_1", "enemy_inst_1"]
    assert state.current_turn_index == 0

    errors = state.advance_turn(session)
    assert errors == []
    assert state.current_turn_index == 1

    errors = state.handle_end_turn(session)
    assert errors == []
    assert state.current_turn_index == 0


def test_placeholder_action_handlers_return_not_implemented() -> None:
    session = _session_with_party()
    state = EncounterState()

    errors = state.handle_attack(session, create_action(ActionType.ATTACK, parameters={}))
    assert errors and "No active encounter" in errors[0]

    errors = state.handle_cast_spell(session, create_action(ActionType.CAST_SPELL, parameters={}))
    assert errors and "No active encounter" in errors[0]

    errors = state.start_encounter(session, _encounter())
    assert errors == []

    errors = state.handle_attack(
        session,
        create_action(
            ActionType.ATTACK,
            parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_inst_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert errors and "not implemented yet" in errors[0]

    errors = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_1", "target_instance_ids": ["enemy_inst_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert errors and "not implemented yet" in errors[0]


def test_handle_action_routes_and_validates_turn_owner() -> None:
    session = _session_with_party()
    state = EncounterState()

    errors = state.start_encounter(session, _encounter())
    assert errors == []

    wrong_actor_attack = create_action(
        ActionType.ATTACK,
        parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_inst_1"]},
        actor_instance_id="enemy_inst_1",
    )
    errors = state.handle_action(session, wrong_actor_attack)
    assert errors and "invalid for current turn" in errors[0]

    end_turn = create_action(ActionType.END_TURN, actor_instance_id="player_1")
    errors = state.handle_action(session, end_turn)
    assert errors == []
    assert state.current_turn_index == 1

    bad_attack_type = create_action(
        ActionType.END_TURN,
        actor_instance_id="enemy_inst_1",
    )
    errors = state.handle_attack(session, bad_attack_type)
    assert errors and "Invalid action type" in errors[0]


def test_end_encounter_transitions_back_to_exploration() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()

    errors = state.end_encounter(session)
    assert errors and "No active encounter" in errors[0]

    errors = state.start_encounter(session, encounter)
    assert errors == []

    errors = state.end_encounter(session)
    assert errors == []
    assert session.state is GameState.EXPLORATION
    assert state.current_encounter is None
    assert state.turn_order == []
    assert state.current_turn_index == 0
    assert state.post_encounter_summary["encounter_id"] == "enc_1"
    assert encounter.cleared is True
