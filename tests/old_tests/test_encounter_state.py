from types import SimpleNamespace
from unittest.mock import patch

from game.core.action import create_action
from game.core.enums import ActionType
from game.actors.enemy import create_enemy
from game.combat.attack import Attack
from game.combat.spell import Spell
from game.combat.status_effect import StatusEffect, StatusEffectInstance
from game.dungeons.dungeon import Encounter
from game.entity.blocks.archetype import Archetype, WeaponConstraints
from game.entity.blocks.race import Race
from game.entity.blocks.weapon import Weapon
from game.enums import (
    AttackType,
    ControlType,
    DamageType,
    SpellType,
    DifficultyType,
    GameState,
    StatusEffectType,
    WeaponDelivery,
    WeaponHandling,
    WeaponMagicType,
    WeaponProficiency,
    WeaponWeightClass,
)
from game.states.encounter import EncounterState
from game.states.pregame import PreGameState
from game.combat.resolution import calculate_damage_multiplier


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
    result = pregame.handle_create_player(
        session,
        id="player_1",
        name="Player",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )
    assert result.ok is True
    return session


def _encounter() -> Encounter:
    enemy = create_enemy(
        id="enemy_1",
        name="Enemy",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
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


def _basic_attack() -> Attack:
    return Attack(
        id="attack_1",
        name="Strike",
        description="",
        type=AttackType.MELEE,
        parameters={"damage_roll": "1d6+0", "hit_modifiers": 2},
    )


def _basic_spell() -> Spell:
    return Spell(
        id="spell_1",
        name="Arc Bolt",
        description="",
        type=SpellType.ATTACK,
        spell_cost=1,
        parameters={"damage_roll": "1d6+0", "hit_modifiers": 2},
    )


def _enemy(instance_id: str, enemy_id: str) -> object:
    return create_enemy(
        id=enemy_id,
        name=f"Enemy {enemy_id}",
        description="",
        race=_race(),
        archetype=_archetype(),
        weapons=[_weapon()],
    )


def _control_effect(control_type: ControlType, effect_id: str) -> StatusEffectInstance:
    return StatusEffectInstance(
        status_effect=StatusEffect(
            id=effect_id,
            name=f"{control_type.value}_effect",
            description="",
            type=StatusEffectType.CONTROL,
            parameters={"control_type": control_type.value},
        ),
        duration=2,
    )


def test_start_and_advance_turn_placeholder_flow() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()

    result = state.start_encounter(session, encounter)
    assert result.ok is True
    assert session.state is GameState.ENCOUNTER
    assert state.current_encounter is encounter
    assert state.turn_order == ["player_1", "enemy_1"]
    assert state.current_turn_index == 0

    result = state.advance_turn(session)
    assert result.ok is True
    assert state.current_turn_index == 1

    result = state.handle_end_turn(session)
    assert result.ok is True
    assert state.current_turn_index == 0


def test_start_encounter_uses_initiative_ordering() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()

    with patch("game.combat.initiative.roll_for_initiative", side_effect=[3, 18]):
        result = state.start_encounter(session, encounter)

    assert result.ok is True
    assert state.turn_order == ["enemy_1", "player_1"]
    assert any(event["type"] == "initiative_result" for event in result.events)
    assert any(event["type"] == "dice_rolled" for event in result.events)
    assert any(event["type"] == "dice_result" for event in result.events)
    assert state.current_turn_index == 0


def test_start_encounter_uses_initiative_modifiers_when_rolls_tie() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    encounter.enemies[0].initiative_mod = 4

    with patch("game.combat.initiative.roll_for_initiative", side_effect=[10, 10]):
        result = state.start_encounter(session, encounter)

    assert result.ok is True
    assert state.turn_order[0] == "enemy_1"


def test_advance_turn_skips_control_locked_actor() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    assert state.start_encounter(session, encounter).ok is True

    encounter.enemies[0].active_status_effects.append(_control_effect(ControlType.STUNNED, "stun_enemy"))

    result = state.handle_end_turn(session, create_action(ActionType.END_TURN, actor_instance_id="player_1"))
    assert result.ok is True
    assert state.turn_order[state.current_turn_index] == "player_1"
    assert any(event["type"] == "turn_skipped" for event in result.events)


def test_turn_started_event_includes_enemy_persona() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    encounter.enemies[0].initiative_mod = 0
    encounter.enemies[0].persona = "aggressive_brute"

    with patch("game.combat.initiative.roll_for_initiative", side_effect=[5, 5]):
        result = state.start_encounter(session, encounter)
    assert result.ok is True
    assert state.turn_order[0] == "player_1"

    # Player ends turn, enemy turn starts and should include persona context.
    result = state.handle_end_turn(
        session,
        create_action(ActionType.END_TURN, actor_instance_id="player_1"),
    )
    assert result.ok is True
    turn_started_events = [event for event in result.events if event["type"] == "turn_started"]
    assert turn_started_events
    assert turn_started_events[0].get("persona") == "aggressive_brute"
    assert isinstance(turn_started_events[0].get("turn_index"), int)


def test_action_handlers_resolve_combat_actions() -> None:
    session = _session_with_party()
    state = EncounterState()

    result = state.handle_attack(session, create_action(ActionType.ATTACK, parameters={}))
    assert result.errors and "No active encounter" in result.errors[0]

    result = state.handle_cast_spell(session, create_action(ActionType.CAST_SPELL, parameters={}))
    assert result.errors and "No active encounter" in result.errors[0]

    result = state.start_encounter(session, _encounter())
    assert result.ok is True

    session.party[0].known_attacks = [_basic_attack()]
    session.party[0].known_spells = [_basic_spell()]

    with patch("game.combat.resolution.roll_save_throw", return_value=20), patch(
        "game.combat.resolution.roll_dice", return_value=4
    ):
        result = state.handle_attack(
            session,
            create_action(
                ActionType.ATTACK,
                parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_1"]},
                actor_instance_id="player_1",
            ),
        )
    assert result.ok is True
    assert any(event["type"] == "damage_applied" for event in result.events)
    assert state.current_encounter.enemies[0].hp < state.current_encounter.enemies[0].max_hp

    spell_slots_before = session.party[0].spell_slots
    with patch("game.combat.resolution.roll_save_throw", return_value=20), patch(
        "game.combat.resolution.roll_dice", return_value=5
    ):
        result = state.handle_cast_spell(
            session,
            create_action(
                ActionType.CAST_SPELL,
                parameters={"spell_id": "spell_1", "target_instance_ids": ["enemy_1"]},
                actor_instance_id="player_1",
            ),
        )
    assert result.ok is True
    assert session.party[0].spell_slots == spell_slots_before - 1
    assert any(event["type"] == "spell_cast" for event in result.events)


def test_handle_action_routes_and_validates_turn_owner() -> None:
    session = _session_with_party()
    state = EncounterState()

    result = state.start_encounter(session, _encounter())
    assert result.ok is True

    wrong_actor_attack = create_action(
        ActionType.ATTACK,
        parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_1"]},
        actor_instance_id="enemy_1",
    )
    result = state.handle_action(session, wrong_actor_attack)
    assert result.errors and "invalid for current turn" in result.errors[0]

    end_turn = create_action(ActionType.END_TURN, actor_instance_id="player_1")
    result = state.handle_action(session, end_turn)
    assert result.ok is True
    assert state.current_turn_index == 1

    bad_attack_type = create_action(
        ActionType.END_TURN,
        actor_instance_id="enemy_1",
    )
    result = state.handle_attack(session, bad_attack_type)
    assert result.errors and "Invalid action type" in result.errors[0]


def test_end_encounter_transitions_back_to_exploration() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()

    result = state.end_encounter(session)
    assert result.errors and "No active encounter" in result.errors[0]

    result = state.start_encounter(session, encounter)
    assert result.ok is True

    session.party[0].active_status_effects.extend(
        [
            _control_effect(ControlType.RESTRAINED, "restrained_end_1"),
            _control_effect(ControlType.SILENCED, "silenced_end_1"),
        ]
    )
    assert len(session.party[0].active_status_effects) == 2

    result = state.end_encounter(session)
    assert result.ok is True
    assert session.state is GameState.EXPLORATION
    assert state.current_encounter is None
    assert state.turn_order == []
    assert state.current_turn_index == 0
    assert state.post_encounter_summary["encounter_id"] == "enc_1"
    assert state.post_encounter_summary["clear_reward"] == 10
    assert state.post_encounter_summary["session_points"] == 10
    assert state.post_encounter_summary["status"] == "cleared"
    assert encounter.cleared is True
    assert session.party[0].active_status_effects == []
    assert any(
        event["type"] == "status_effect_removed"
        and event.get("target_instance_id") == "player_1"
        and event.get("count") == 2
        and event.get("source") == "encounter_end"
        for event in result.events
    )


def test_result_first_lifecycle_methods() -> None:
    session = _session_with_party()
    state = EncounterState()

    result = state.start_encounter(session, _encounter())
    assert result.ok is True
    assert session.state is GameState.ENCOUNTER

    result = state.advance_turn(session)
    assert result.ok is True

    result = state.end_encounter(session)
    assert result.ok is True
    assert session.state is GameState.EXPLORATION


def test_restrained_actor_cannot_attack() -> None:
    session = _session_with_party()
    state = EncounterState()
    assert state.start_encounter(session, _encounter()).ok is True

    session.party[0].known_attacks = [_basic_attack()]
    session.party[0].active_status_effects.append(
        _control_effect(ControlType.RESTRAINED, "restrained_1")
    )

    result = state.handle_attack(
        session,
        create_action(
            ActionType.ATTACK,
            parameters={"attack_id": "attack_1", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.errors and "Restrained actors cannot attack" in result.errors[0]


def test_silenced_actor_cannot_cast_spell() -> None:
    session = _session_with_party()
    state = EncounterState()
    assert state.start_encounter(session, _encounter()).ok is True

    session.party[0].known_spells = [_basic_spell()]
    session.party[0].active_status_effects.append(
        _control_effect(ControlType.SILENCED, "silenced_1")
    )

    result = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_1", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.errors and "Silenced actors cannot cast spells" in result.errors[0]


def test_single_target_rejects_multi_target_but_aoe_allows_it() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    encounter.enemies.append(_enemy("enemy_inst_2", "enemy_2"))
    assert state.start_encounter(session, encounter).ok is True

    single_target_attack = Attack(
        id="attack_single",
        name="Single Strike",
        description="",
        type=AttackType.MELEE,
        parameters={"damage_roll": "1d6+0", "hit_modifiers": 2},
    )
    aoe_attack = Attack(
        id="attack_aoe",
        name="Sweep",
        description="",
        type=AttackType.AOE_MELEE,
        parameters={"damage_roll": "1d6+0", "hit_modifiers": 2},
    )
    session.party[0].known_attacks = [single_target_attack, aoe_attack]

    result = state.handle_attack(
        session,
        create_action(
            ActionType.ATTACK,
            parameters={
                "attack_id": "attack_single",
                "target_instance_ids": ["enemy_1", "enemy_2"],
            },
            actor_instance_id="player_1",
        ),
    )
    assert result.errors and "Single-target actions must include exactly one" in result.errors[0]

    with patch("game.combat.resolution.roll_save_throw", return_value=20), patch(
        "game.combat.resolution.roll_dice", return_value=3
    ):
        result = state.handle_attack(
            session,
            create_action(
                ActionType.ATTACK,
                parameters={
                    "attack_id": "attack_aoe",
                    "target_instance_ids": ["enemy_1", "enemy_2"],
                },
                actor_instance_id="player_1",
            ),
        )
    assert result.ok is True
    assert len([event for event in result.events if event["type"] == "damage_applied"]) == 2


def test_cleanse_removes_control_effects() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    assert state.start_encounter(session, encounter).ok is True

    dot_effect = StatusEffectInstance(
        status_effect=StatusEffect(
            id="dot_1",
            name="dot",
            description="",
            type=StatusEffectType.DOT,
            parameters={},
        ),
        duration=2,
    )
    encounter.enemies[0].active_status_effects = [
        _control_effect(ControlType.STUNNED, "stun_1"),
        dot_effect,
    ]

    cleanse_spell = Spell(
        id="spell_cleanse",
        name="Cleanse",
        description="",
        type=SpellType.CLEANSE,
        spell_cost=1,
        parameters={
            "cleanse_status_effect_types": [StatusEffectType.CONTROL.value],
            "cleanse_control_types": [ControlType.STUNNED.value],
        },
    )
    session.party[0].known_spells = [cleanse_spell]

    result = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_cleanse", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.ok is True
    assert any(event["type"] == "status_effect_removed" for event in result.events)
    assert len(encounter.enemies[0].active_status_effects) == 1
    assert encounter.enemies[0].active_status_effects[0].status_effect.type is StatusEffectType.DOT


def test_status_effect_overwrite_and_stack_rules() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    assert state.start_encounter(session, encounter).ok is True

    atk_mod_low = StatusEffectInstance(
        status_effect=StatusEffect(
            id="atk_mod_low",
            name="atk_low",
            description="",
            type=StatusEffectType.ATKMOD,
            parameters={"modifier": 1},
        ),
        duration=2,
    )
    atk_mod_high = StatusEffectInstance(
        status_effect=StatusEffect(
            id="atk_mod_high",
            name="atk_high",
            description="",
            type=StatusEffectType.ATKMOD,
            parameters={"modifier": 3},
        ),
        duration=4,
    )
    ac_mod_a = StatusEffectInstance(
        status_effect=StatusEffect(
            id="ac_mod_a",
            name="ac_a",
            description="",
            type=StatusEffectType.ACMOD,
            parameters={"modifier": 1},
        ),
        duration=2,
    )
    ac_mod_b = StatusEffectInstance(
        status_effect=StatusEffect(
            id="ac_mod_b",
            name="ac_b",
            description="",
            type=StatusEffectType.ACMOD,
            parameters={"modifier": 2},
        ),
        duration=2,
    )

    spell_atk_mod_1 = Spell(
        id="spell_atk_mod_1",
        name="atk_mod_1",
        description="",
        type=SpellType.DEBUFF,
        spell_cost=0,
        parameters={
            "applied_status_effects": [
                {"status_effect": atk_mod_low.status_effect.to_dict(), "duration": 2}
            ]
        },
    )
    spell_atk_mod_2 = Spell(
        id="spell_atk_mod_2",
        name="atk_mod_2",
        description="",
        type=SpellType.DEBUFF,
        spell_cost=0,
        parameters={
            "applied_status_effects": [
                {"status_effect": atk_mod_high.status_effect.to_dict(), "duration": 4}
            ]
        },
    )
    spell_ac_mod = Spell(
        id="spell_ac_mod",
        name="ac_mod",
        description="",
        type=SpellType.BUFF,
        spell_cost=0,
        parameters={
            "applied_status_effects": [
                {"status_effect": ac_mod_a.status_effect.to_dict(), "duration": 2},
                {"status_effect": ac_mod_b.status_effect.to_dict(), "duration": 2},
            ]
        },
    )
    session.party[0].known_spells = [spell_atk_mod_1, spell_atk_mod_2, spell_ac_mod]

    result = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_atk_mod_1", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.ok is True

    result = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_atk_mod_2", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.ok is True
    enemy_effects = encounter.enemies[0].active_status_effects
    assert len([e for e in enemy_effects if e.status_effect.type is StatusEffectType.ATKMOD]) == 1
    assert any(e.status_effect.id == "atk_mod_high" for e in enemy_effects)

    result = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_ac_mod", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.ok is True
    enemy_effects = encounter.enemies[0].active_status_effects
    acmods = [e for e in enemy_effects if e.status_effect.type is StatusEffectType.ACMOD]
    assert len(acmods) == 1
    assert acmods[0].status_effect.id == "ac_mod_b"


def test_end_turn_ticks_dot_and_hot_and_decrements_duration() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    assert state.start_encounter(session, encounter).ok is True

    dot_effect = StatusEffectInstance(
        status_effect=StatusEffect(
            id="dot_burn",
            name="burn",
            description="",
            type=StatusEffectType.DOT,
            parameters={"damage_types": [DamageType.FIRE.value], "damage_value": 3},
        ),
        duration=2,
    )
    hot_effect = StatusEffectInstance(
        status_effect=StatusEffect(
            id="hot_regen",
            name="regen",
            description="",
            type=StatusEffectType.HOT,
            parameters={"heal_value": 2},
        ),
        duration=2,
    )

    encounter.enemies[0].active_status_effects = [dot_effect]
    session.party[0].hp = session.party[0].max_hp - 3
    session.party[0].active_status_effects = [hot_effect]

    enemy_hp_before = encounter.enemies[0].hp
    player_hp_before = session.party[0].hp
    result = state.handle_end_turn(
        session,
        create_action(ActionType.END_TURN, actor_instance_id="player_1"),
    )

    assert result.ok is True
    assert encounter.enemies[0].hp == enemy_hp_before - 3
    assert session.party[0].hp == min(session.party[0].max_hp, player_hp_before + 2)
    assert encounter.enemies[0].active_status_effects[0].duration == 1
    assert session.party[0].active_status_effects[0].duration == 1


def test_calculate_damage_multiplier_precedence() -> None:
    assert calculate_damage_multiplier(DamageType.FIRE, [DamageType.FIRE], [], []) == 0.0
    assert calculate_damage_multiplier(DamageType.FIRE, [], [DamageType.FIRE], []) == 0.5
    assert calculate_damage_multiplier(DamageType.FIRE, [], [], [DamageType.FIRE]) == 2.0
    assert calculate_damage_multiplier(DamageType.FIRE, [], [DamageType.FIRE], [DamageType.FIRE]) == 1.0


def test_attack_damage_respects_resistance_and_immunity() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    assert state.start_encounter(session, encounter).ok is True

    fire_attack = Attack(
        id="attack_fire",
        name="Fire Strike",
        description="",
        type=AttackType.MELEE,
        parameters={
            "damage_roll": "1d10+0",
            "hit_modifiers": 5,
            "damage_types": [DamageType.FIRE.value],
        },
    )
    session.party[0].known_attacks = [fire_attack]

    encounter.enemies[0].resistances = [DamageType.FIRE]
    hp_before = encounter.enemies[0].hp
    with patch("game.combat.resolution.roll_save_throw", return_value=20), patch(
        "game.combat.resolution.roll_dice", return_value=8
    ):
        result = state.handle_attack(
            session,
            create_action(
                ActionType.ATTACK,
                parameters={"attack_id": "attack_fire", "target_instance_ids": ["enemy_1"]},
                actor_instance_id="player_1",
            ),
        )
    assert result.ok is True
    assert encounter.enemies[0].hp == hp_before - 4

    encounter.enemies[0].immunities = [DamageType.FIRE]
    hp_before = encounter.enemies[0].hp
    with patch("game.combat.resolution.roll_save_throw", return_value=20), patch(
        "game.combat.resolution.roll_dice", return_value=8
    ):
        result = state.handle_attack(
            session,
            create_action(
                ActionType.ATTACK,
                parameters={"attack_id": "attack_fire", "target_instance_ids": ["enemy_1"]},
                actor_instance_id="player_1",
            ),
        )
    assert result.ok is True
    assert encounter.enemies[0].hp == hp_before


def test_cast_spell_fails_with_insufficient_spell_slots() -> None:
    session = _session_with_party()
    state = EncounterState()
    assert state.start_encounter(session, _encounter()).ok is True

    expensive_spell = Spell(
        id="spell_expensive",
        name="Big Spell",
        description="",
        type=SpellType.ATTACK,
        spell_cost=2,
        parameters={"damage_roll": "1d6+0", "hit_modifiers": 2},
    )
    session.party[0].known_spells = [expensive_spell]
    session.party[0].spell_slots = 1

    result = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_expensive", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.errors and "Not enough spell slots" in result.errors[0]


def test_heal_spell_caps_at_max_hp_and_rejects_dead_target() -> None:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    assert state.start_encounter(session, encounter).ok is True

    heal_spell = Spell(
        id="spell_heal",
        name="Heal",
        description="",
        type=SpellType.HEAL,
        spell_cost=1,
        parameters={"heal_roll": "1d8+0"},
    )
    session.party[0].known_spells = [heal_spell]

    encounter.enemies[0].hp = encounter.enemies[0].max_hp - 1
    with patch("game.combat.resolution.roll_dice", return_value=10):
        result = state.handle_cast_spell(
            session,
            create_action(
                ActionType.CAST_SPELL,
                parameters={"spell_id": "spell_heal", "target_instance_ids": ["enemy_1"]},
                actor_instance_id="player_1",
            ),
        )
    assert result.ok is True
    assert encounter.enemies[0].hp == encounter.enemies[0].max_hp

    encounter.enemies[0].hp = 0
    result = state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": "spell_heal", "target_instance_ids": ["enemy_1"]},
            actor_instance_id="player_1",
        ),
    )
    assert result.errors and "is not alive" in result.errors[0]
