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
    DifficultyType,
    GameState,
    SpellType,
    StatusEffectType,
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
        base_hp=20,
        base_AC=10,
        base_spell_slots=3,
    )


def _archetype() -> Archetype:
    return Archetype(
        id="arch_1",
        name="Archetype",
        description="",
        hp_mod=0,
        AC_mod=0,
        spell_slot_mod=0,
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
        points=0,
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


def _start_encounter() -> tuple[SimpleNamespace, EncounterState, Encounter]:
    session = _session_with_party()
    state = EncounterState()
    encounter = _encounter()
    result = state.start_encounter(session, encounter)
    assert result.ok is True
    return session, state, encounter


def _effect(
    effect_id: str,
    effect_type: StatusEffectType,
    duration: int,
    *,
    modifier: int = 0,
    damage_type: DamageType | None = None,
    damage_value: int = 0,
    heal_value: int = 0,
    control_type: ControlType | None = None,
) -> StatusEffectInstance:
    parameters: dict = {}
    if modifier:
        parameters["modifier"] = modifier
    if damage_type is not None:
        parameters["damage_types"] = [damage_type.value]
    if damage_value:
        parameters["damage_value"] = damage_value
    if heal_value:
        parameters["heal_value"] = heal_value
    if control_type is not None:
        parameters["control_type"] = control_type.value

    return StatusEffectInstance(
        status_effect=StatusEffect(
            id=effect_id,
            name=effect_id,
            description="",
            type=effect_type,
            parameters=parameters,
        ),
        duration=duration,
    )


def _effect_payload(effect_instance: StatusEffectInstance) -> dict:
    return {
        "status_effect": effect_instance.status_effect.to_dict(),
        "duration": effect_instance.duration,
    }


def _cast_spell(state: EncounterState, session: SimpleNamespace, spell_id: str, target_id: str = "enemy_1"):
    return state.handle_cast_spell(
        session,
        create_action(
            ActionType.CAST_SPELL,
            parameters={"spell_id": spell_id, "target_instance_ids": [target_id]},
            actor_instance_id="player_1",
        ),
    )


def _attack(state: EncounterState, session: SimpleNamespace, attack_id: str, target_id: str = "enemy_1"):
    return state.handle_attack(
        session,
        create_action(
            ActionType.ATTACK,
            parameters={"attack_id": attack_id, "target_instance_ids": [target_id]},
            actor_instance_id="player_1",
        ),
    )


def test_damage_calculation_resistance_and_vulnerability_cancel() -> None:
    session, state, encounter = _start_encounter()

    attack = Attack(
        id="atk_fire",
        name="fire",
        description="",
        type=AttackType.MELEE,
        parameters={"damage_roll": "1d10+0", "hit_modifiers": 5, "damage_types": [DamageType.FIRE.value]},
    )
    session.party[0].known_attacks = [attack]

    target = encounter.enemies[0]
    target.resistances = [DamageType.FIRE]
    target.vulnerabilities = [DamageType.FIRE]

    hp_before = target.hp
    with patch("game.combat.resolution.roll_save_throw", return_value=20), patch(
        "game.combat.resolution.roll_dice", return_value=8
    ):
        result = _attack(state, session, "atk_fire")

    assert result.ok is True
    assert target.hp == hp_before - 8


def test_damage_calculation_status_effect_immunity_zeroes_damage() -> None:
    session, state, encounter = _start_encounter()

    attack = Attack(
        id="atk_fire",
        name="fire",
        description="",
        type=AttackType.MELEE,
        parameters={"damage_roll": "1d10+0", "hit_modifiers": 5, "damage_types": [DamageType.FIRE.value]},
    )
    session.party[0].known_attacks = [attack]

    target = encounter.enemies[0]
    target.active_status_effects = [
        _effect("imm_fire", StatusEffectType.IMMUNITY, 2, damage_type=DamageType.FIRE)
    ]

    hp_before = target.hp
    with patch("game.combat.resolution.roll_save_throw", return_value=20), patch(
        "game.combat.resolution.roll_dice", return_value=9
    ):
        result = _attack(state, session, "atk_fire")

    assert result.ok is True
    assert target.hp == hp_before


def test_skipping_turn_when_target_has_stunned_control() -> None:
    session, state, encounter = _start_encounter()
    encounter.enemies[0].active_status_effects = [
        _effect("stun_enemy", StatusEffectType.CONTROL, 2, control_type=ControlType.STUNNED)
    ]

    result = state.handle_end_turn(
        session,
        create_action(ActionType.END_TURN, actor_instance_id="player_1"),
    )

    assert result.ok is True
    assert any(
        event.get("type") == "turn_skipped" and event.get("actor_instance_id") == "enemy_1"
        for event in result.events
    )
    assert state.current_turn_index == 0


def test_apply_stack_and_overwrite_rules_for_status_effects() -> None:
    session, state, encounter = _start_encounter()

    atk_mod_low = _effect("atk_mod_low", StatusEffectType.ATKMOD, 2, modifier=1)
    atk_mod_high = _effect("atk_mod_high", StatusEffectType.ATKMOD, 4, modifier=3)
    ac_mod_a = _effect("ac_mod_a", StatusEffectType.ACMOD, 2, modifier=1)
    ac_mod_b = _effect("ac_mod_b", StatusEffectType.ACMOD, 2, modifier=2)
    dot_fire_low = _effect("dot_fire_low", StatusEffectType.DOT, 3, damage_type=DamageType.FIRE, damage_value=2)
    dot_fire_high = _effect("dot_fire_high", StatusEffectType.DOT, 5, damage_type=DamageType.FIRE, damage_value=4)

    spell = Spell(
        id="spell_status",
        name="status",
        description="",
        type=SpellType.DEBUFF,
        spell_cost=0,
        parameters={
            "applied_status_effects": [
                _effect_payload(atk_mod_low),
                _effect_payload(ac_mod_a),
                _effect_payload(dot_fire_low),
            ]
        },
    )
    spell_overwrite = Spell(
        id="spell_status_overwrite",
        name="status_overwrite",
        description="",
        type=SpellType.DEBUFF,
        spell_cost=0,
        parameters={
            "applied_status_effects": [
                _effect_payload(atk_mod_high),
                _effect_payload(ac_mod_b),
                _effect_payload(dot_fire_high),
            ]
        },
    )
    session.party[0].known_spells = [spell, spell_overwrite]

    first = _cast_spell(state, session, "spell_status")
    second = _cast_spell(state, session, "spell_status_overwrite")

    assert first.ok is True
    assert second.ok is True

    effects = encounter.enemies[0].active_status_effects
    atkmods = [e for e in effects if e.status_effect.type is StatusEffectType.ATKMOD]
    acmods = [e for e in effects if e.status_effect.type is StatusEffectType.ACMOD]
    fire_dots = [
        e
        for e in effects
        if e.status_effect.type is StatusEffectType.DOT
        and e.status_effect.damage_types
        and e.status_effect.damage_types[0] is DamageType.FIRE
    ]

    assert len(atkmods) == 1
    assert atkmods[0].status_effect.id == "atk_mod_high"
    assert len(acmods) == 1
    assert acmods[0].status_effect.id == "ac_mod_b"
    assert len(fire_dots) == 1
    assert fire_dots[0].status_effect.id == "dot_fire_high"


def test_cleanse_removes_by_status_effect_type_and_control_type() -> None:
    session, state, encounter = _start_encounter()

    target = encounter.enemies[0]
    target.active_status_effects = [
        _effect("stun", StatusEffectType.CONTROL, 2, control_type=ControlType.STUNNED),
        _effect("restrain", StatusEffectType.CONTROL, 2, control_type=ControlType.RESTRAINED),
        _effect("dot_fire", StatusEffectType.DOT, 2, damage_type=DamageType.FIRE, damage_value=2),
    ]

    cleanse = Spell(
        id="cleanse",
        name="cleanse",
        description="",
        type=SpellType.CLEANSE,
        spell_cost=0,
        parameters={
            "cleanse_status_effect_types": [StatusEffectType.CONTROL.value],
            "cleanse_control_types": [ControlType.STUNNED.value],
        },
    )
    session.party[0].known_spells = [cleanse]

    result = _cast_spell(state, session, "cleanse")
    assert result.ok is True

    remaining = target.active_status_effects
    assert len(remaining) == 1
    assert remaining[0].status_effect.type is StatusEffectType.DOT


def test_cc_immunity_blocks_control_application() -> None:
    session, state, encounter = _start_encounter()

    cc_immunity = _effect(
        "immune_stun",
        StatusEffectType.CC_IMMUNITY,
        3,
        control_type=ControlType.STUNNED,
    )
    control_stun = _effect(
        "apply_stun",
        StatusEffectType.CONTROL,
        2,
        control_type=ControlType.STUNNED,
    )

    encounter.enemies[0].active_status_effects = [cc_immunity]
    control_spell = Spell(
        id="stun_spell",
        name="stun",
        description="",
        type=SpellType.CONTROL,
        spell_cost=0,
        parameters={"applied_status_effects": [_effect_payload(control_stun)]},
    )
    session.party[0].known_spells = [control_spell]

    result = _cast_spell(state, session, "stun_spell")
    assert result.ok is True

    controls = [
        effect
        for effect in encounter.enemies[0].active_status_effects
        if effect.status_effect.type is StatusEffectType.CONTROL
    ]
    assert len(controls) == 0


def test_restrained_blocks_attack_and_silenced_blocks_cast() -> None:
    session, state, _ = _start_encounter()

    attack = Attack(
        id="atk",
        name="atk",
        description="",
        type=AttackType.MELEE,
        parameters={"damage_roll": "1d6+0", "hit_modifiers": 2},
    )
    spell = Spell(
        id="spl",
        name="spl",
        description="",
        type=SpellType.ATTACK,
        spell_cost=0,
        parameters={"damage_roll": "1d6+0", "hit_modifiers": 2},
    )
    session.party[0].known_attacks = [attack]
    session.party[0].known_spells = [spell]

    session.party[0].active_status_effects = [
        _effect("restrain", StatusEffectType.CONTROL, 2, control_type=ControlType.RESTRAINED)
    ]
    attack_result = _attack(state, session, "atk")
    assert attack_result.errors and "Restrained actors cannot attack" in attack_result.errors[0]

    session.party[0].active_status_effects = [
        _effect("silence", StatusEffectType.CONTROL, 2, control_type=ControlType.SILENCED)
    ]
    cast_result = _cast_spell(state, session, "spl")
    assert cast_result.errors and "Silenced actors cannot cast spells" in cast_result.errors[0]


def test_end_turn_ticks_dot_and_hot_for_all_alive_actors() -> None:
    session, state, encounter = _start_encounter()

    player = session.party[0]
    enemy = encounter.enemies[0]

    player.hp = player.max_hp - 5
    player.active_status_effects = [
        _effect("hot", StatusEffectType.HOT, 2, heal_value=3)
    ]
    enemy.active_status_effects = [
        _effect("dot", StatusEffectType.DOT, 2, damage_type=DamageType.POISON, damage_value=4)
    ]

    enemy_hp_before = enemy.hp
    player_hp_before = player.hp

    result = state.handle_end_turn(
        session,
        create_action(ActionType.END_TURN, actor_instance_id="player_1"),
    )

    assert result.ok is True
    assert enemy.hp == enemy_hp_before - 4
    assert player.hp == min(player.max_hp, player_hp_before + 3)
    assert enemy.active_status_effects[0].duration == 1
    assert player.active_status_effects[0].duration == 1
    assert any(event.get("type") == "status_effect_ticked" for event in result.events)
