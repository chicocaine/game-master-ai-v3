from __future__ import annotations


import math
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Tuple

from game.core.action import Action
from game.core.action_result import ActionResult
from game.core.enums import EventType

from game.util.dice import roll_dice, roll_save_throw
from game.enums import AttackType, SpellType, ControlType, DamageType, StatusEffectType
from game.combat.status_effect import (
    StatusEffectInstance,
    apply_status_effect_instances,
    merged_control_immunities_from_effects,
    merged_damage_affinities_from_effects,
    total_ac_modifier_from_effects,
    total_attack_modifier_from_effects,
)
from game.combat.attack import Attack
from game.combat.spell import Spell
from game.runtime.models import EncounterInstance

if TYPE_CHECKING:
    from game.states.game_session import GameSession


def calculate_damage_multiplier(
    attack_damage_type: DamageType,
    target_immunities: List[DamageType],
    target_resistances: List[DamageType],
    target_vulnerabilities: List[DamageType],
) -> float:
    if attack_damage_type in target_immunities:
        return 0.0

    has_resistance = attack_damage_type in target_resistances
    has_vulnerability = attack_damage_type in target_vulnerabilities

    if has_resistance and has_vulnerability:
        return 1.0
    if has_resistance:
        return 0.5
    if has_vulnerability:
        return 2.0
    return 1.0


def _normalize_target_ids(raw: object) -> List[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def _instance_id(actor: Any) -> str:
    return str(getattr(actor, "player_instance_id", "") or getattr(actor, "enemy_instance_id", ""))


def _all_actors(session: "GameSession", encounter: EncounterInstance) -> List[Any]:
    return [*session.party, *encounter.enemies]


def _alive_actors(session: "GameSession", encounter: EncounterInstance) -> List[Any]:
    return [actor for actor in _all_actors(session, encounter) if getattr(actor, "hp", 0) > 0]


def _find_actor_by_instance_id(session: "GameSession", encounter: EncounterInstance, instance_id: str) -> Any | None:
    for actor in _all_actors(session, encounter):
        if _instance_id(actor) == instance_id:
            return actor
    return None


def _find_attack(actor: Any, attack_id: str) -> Attack | None:
    for attack in getattr(actor, "merged_attacks", []):
        if attack.id == attack_id:
            return attack
    return None


def _find_spell(actor: Any, spell_id: str) -> Spell | None:
    for spell in getattr(actor, "merged_spells", []):
        if spell.id == spell_id:
            return spell
    return None


def _has_control_effect(actor: Any, control_type: ControlType) -> bool:
    for effect_instance in getattr(actor, "active_status_effects", []):
        if effect_instance.duration <= 0:
            continue
        status_effect = effect_instance.status_effect
        if status_effect.type == StatusEffectType.CONTROL and status_effect.control_type == control_type:
            return True
    return False


def _apply_damage(target: Any, amount: int) -> int:
    before_hp = getattr(target, "hp", 0)
    target.hp = max(0, before_hp - max(0, amount))
    return before_hp - target.hp


def _apply_heal(target: Any, amount: int) -> int:
    before_hp = getattr(target, "hp", 0)
    target.hp = min(getattr(target, "max_hp", before_hp), before_hp + max(0, amount))
    return target.hp - before_hp


def _apply_status_effects(target: Any, effects: List[StatusEffectInstance]) -> int:
    if not effects:
        return 0
    return apply_status_effect_instances(target.active_status_effects, effects)


def _can_apply_status_effect(target: Any, effect_instance: StatusEffectInstance) -> bool:
    effect = effect_instance.status_effect
    if effect.type != StatusEffectType.CONTROL:
        return True
    control_immunities = set(getattr(target, "merged_cc_immunities", []))
    control_immunities.update(merged_control_immunities_from_effects(getattr(target, "active_status_effects", [])))
    return effect.control_type not in control_immunities


def _filter_applicable_status_effects(target: Any, effects: List[StatusEffectInstance]) -> List[StatusEffectInstance]:
    return [effect for effect in effects if _can_apply_status_effect(target, effect)]


def _cleanse_status_effects(target: Any, spell: Spell) -> int:
    active_effects = list(getattr(target, "active_status_effects", []))
    if not active_effects:
        return 0
    cleanse_types = set(spell.cleanse_status_effect_types)
    cleanse_control_types = set(spell.cleanse_control_types)

    def _should_remove(effect_instance: StatusEffectInstance) -> bool:
        status_effect = effect_instance.status_effect
        if status_effect.type in cleanse_types:
            return True
        if (
            status_effect.type == StatusEffectType.CONTROL
            and status_effect.control_type in cleanse_control_types
        ):
            return True
        return False

    if not cleanse_types and not cleanse_control_types:
        remaining: List[StatusEffectInstance] = []
    else:
        remaining = [effect for effect in active_effects if not _should_remove(effect)]
    removed_count = len(active_effects) - len(remaining)
    target.active_status_effects = remaining
    return removed_count


def _target_list_for_action(
    session: "GameSession",
    encounter: EncounterInstance,
    raw_target_ids: object,
    is_aoe: bool,
) -> tuple[List[Any], List[str]]:
    target_ids = _normalize_target_ids(raw_target_ids)
    if not target_ids:
        return [], ["At least one target_instance_id is required."]
    if not is_aoe and len(target_ids) != 1:
        return [], ["Single-target actions must include exactly one target_instance_id."]

    targets: List[Any] = []
    errors: List[str] = []
    alive_ids = {_instance_id(actor) for actor in _alive_actors(session, encounter)}
    for target_id in target_ids:
        target = _find_actor_by_instance_id(session, encounter, target_id)
        if target is None:
            errors.append(f"Target '{target_id}' does not exist in this encounter.")
            continue
        if target_id not in alive_ids:
            errors.append(f"Target '{target_id}' is not alive.")
            continue
        targets.append(target)
    return targets, errors


def _merged_damage_affinities(target: Any) -> Tuple[List[DamageType], List[DamageType], List[DamageType]]:
    active_effects = getattr(target, "active_status_effects", [])
    extra_immunities, extra_resistances, extra_vulnerabilities = merged_damage_affinities_from_effects(active_effects)
    target_immunities = list(getattr(target, "merged_immunities", []) or [])
    target_resistances = list(getattr(target, "merged_resistances", []) or [])
    target_vulnerabilities = list(getattr(target, "merged_vulnerabilities", []) or [])
    return (
        sorted(list(set(target_immunities + extra_immunities)), key=lambda item: item.value),
        sorted(list(set(target_resistances + extra_resistances)), key=lambda item: item.value),
        sorted(list(set(target_vulnerabilities + extra_vulnerabilities)), key=lambda item: item.value),
    )


def _damage_amount_for_source(
    *,
    target: Any,
    damage_roll: str,
    damage_types: List[DamageType],
) -> int:
    raw_damage = roll_dice(damage_roll)
    base_damage = max(0, raw_damage)
    primary_damage_type = damage_types[0]
    target_immunities, target_resistances, target_vulnerabilities = _merged_damage_affinities(target)
    multiplier = calculate_damage_multiplier(
        primary_damage_type,
        target_immunities,
        target_resistances,
        target_vulnerabilities,
    )
    return max(0, math.floor(base_damage * multiplier))


def _damage_amount_for_attack(attack: Attack, target: Any) -> int:
    return _damage_amount_for_source(
        target=target,
        damage_roll=attack.damage_roll,
        damage_types=attack.damage_types or [DamageType.FORCE],
    )


def _damage_amount_for_spell(spell: Spell, target: Any) -> int:
    return _damage_amount_for_source(
        target=target,
        damage_roll=spell.damage_roll,
        damage_types=spell.damage_types or [DamageType.FORCE],
    )

def _is_aoe_spell(spell_type: SpellType) -> bool:
    return spell_type in {
        SpellType.AOE_ATTACK,
        SpellType.AOE_HEAL,
        SpellType.AOE_BUFF,
        SpellType.AOE_DEBUFF,
        SpellType.AOE_CONTROL,
        SpellType.AOE_CLEANSE,
    }

def _is_aoe_attack(attack_type: AttackType) -> bool:
    return attack_type in {
        AttackType.AOE_MELEE,
        AttackType.AOE_RANGED,
        AttackType.AOE_UNARMED,
    }

def _is_heal_spell(spell_type: SpellType) -> bool:
    return spell_type in {SpellType.HEAL, SpellType.AOE_HEAL}


def _is_cleanse_spell(spell_type: SpellType) -> bool:
    return spell_type in {SpellType.CLEANSE, SpellType.AOE_CLEANSE}


def _is_status_only_spell(spell_type: SpellType) -> bool:
    return spell_type in {
        SpellType.BUFF,
        SpellType.DEBUFF,
        SpellType.CONTROL,
        SpellType.AOE_BUFF,
        SpellType.AOE_DEBUFF,
        SpellType.AOE_CONTROL,
    }

def _heal_amount_for_spell(spell: Spell) -> int:
    return max(0, roll_dice(spell.heal_roll))


def _roll_attack_check() -> int:
    return roll_save_throw()


def _roll_save_check() -> int:
    return roll_save_throw()


def _hit_requirement_payload(kind: Literal["ac", "save_dc"], target_value: int) -> Dict[str, Any]:
    return {
        "kind": kind,
        "target_value": int(target_value),
    }


def _build_hit_result_payload(
    *,
    base_roll: int,
    modifier_total: int,
    requirement_kind: Literal["ac", "save_dc"],
    requirement_target_value: int,
    passed: bool,
) -> Dict[str, Any]:
    roll_total = int(base_roll + modifier_total)
    return {
        "roll_total": roll_total,
        "base_roll": int(base_roll),
        "modifier_total": int(modifier_total),
        "requirement": _hit_requirement_payload(requirement_kind, requirement_target_value),
        "passed": bool(passed),
    }


def _resolve_hit_result(
    *,
    actor: Any,
    actor_id: str,
    target: Any,
    target_id: str,
    hit_modifiers: int,
    dc: int,
) -> tuple[bool, Dict[str, Any], List[dict]]:
    actor_effect_attack_modifier = total_attack_modifier_from_effects(
        getattr(actor, "active_status_effects", [])
    )
    target_effect_ac_modifier = total_ac_modifier_from_effects(
        getattr(target, "active_status_effects", [])
    )
    effective_target_ac = max(0, getattr(target, "effective_ac", 0) + target_effect_ac_modifier)

    if dc > 0:
        base_roll = _roll_save_check()
        modifier_total = int(getattr(target, "initiative_mod", 0))
        roll_total = int(base_roll + modifier_total)
        passed = roll_total < dc
        hit_result = _build_hit_result_payload(
            base_roll=base_roll,
            modifier_total=modifier_total,
            requirement_kind="save_dc",
            requirement_target_value=dc,
            passed=passed,
        )
        events = [
            {
                "type": EventType.DICE_ROLLED.value,
                "roll_context": "save_throw",
                "actor_instance_id": target_id,
                "notation": "1d20",
                "roll": int(base_roll),
            },
            {
                "type": EventType.DICE_RESULT.value,
                "roll_context": "save_throw",
                "actor_instance_id": target_id,
                "base_roll": int(base_roll),
                "modifier": int(modifier_total),
                "total": int(roll_total),
            },
            {
                "type": EventType.DC_SAVE_THROW_ROLLED.value,
                "actor_instance_id": actor_id,
                "target_instance_id": target_id,
                "base_roll": int(base_roll),
                "modifier": int(modifier_total),
                "total": int(roll_total),
                "dc": int(dc),
                "passed": bool(passed),
            },
        ]
        return passed, hit_result, events

    base_roll = _roll_attack_check()
    modifier_total = int(
        hit_modifiers
        + getattr(actor, "merged_attack_modifier", 0)
        + actor_effect_attack_modifier
    )
    roll_total = int(base_roll + modifier_total)
    passed = roll_total >= effective_target_ac
    hit_result = _build_hit_result_payload(
        base_roll=base_roll,
        modifier_total=modifier_total,
        requirement_kind="ac",
        requirement_target_value=effective_target_ac,
        passed=passed,
    )
    events = [
        {
            "type": EventType.DICE_ROLLED.value,
            "roll_context": "attack_roll",
            "actor_instance_id": actor_id,
            "notation": "1d20",
            "roll": int(base_roll),
        },
        {
            "type": EventType.DICE_RESULT.value,
            "roll_context": "attack_roll",
            "actor_instance_id": actor_id,
            "base_roll": int(base_roll),
            "modifier": int(modifier_total),
            "total": int(roll_total),
        },
    ]
    return passed, hit_result, events


def resolve_attack_action(session: "GameSession", encounter: EncounterInstance, action: Action) -> ActionResult:
    actor = _find_actor_by_instance_id(session, encounter, action.actor_instance_id)
    if actor is None:
        return ActionResult.failure(errors=["Attack actor is not part of the active encounter."])
    if getattr(actor, "hp", 0) <= 0:
        return ActionResult.failure(errors=["Dead actors cannot attack."])
    if _has_control_effect(actor, ControlType.RESTRAINED):
        return ActionResult.failure(errors=["Restrained actors cannot attack."])

    attack_id = str(action.parameters.get("attack_id", ""))
    attack = _find_attack(actor, attack_id)
    if attack is None:
        return ActionResult.failure(errors=[f"Attack '{attack_id}' is not known by actor '{action.actor_instance_id}'."])

    targets, errors = _target_list_for_action(
        session=session,
        encounter=encounter,
        raw_target_ids=action.parameters.get("target_instance_ids", []),
        is_aoe=_is_aoe_attack(attack.type),
    )
    if errors:
        return ActionResult.failure(errors=errors)

    events = [{
        "type": EventType.ATTACK_DECLARED.value,
        "actor_instance_id": action.actor_instance_id,
        "attack_id": attack.id,
        "target_instance_ids": [_instance_id(target) for target in targets],
    }]
    state_changes = {"actors": {}}

    for target in targets:
        target_id = _instance_id(target)
        hit, hit_result, roll_events = _resolve_hit_result(
            actor=actor,
            actor_id=action.actor_instance_id,
            target=target,
            target_id=target_id,
            hit_modifiers=attack.hit_modifiers,
            dc=attack.DC,
        )
        events.extend(roll_events)
        events.append({
            "type": EventType.ATTACK_HIT.value if hit else EventType.ATTACK_MISSED.value,
            "actor_instance_id": action.actor_instance_id,
            "target_instance_id": target_id,
            "attack_id": attack.id,
            "hit_result": hit_result,
        })
        if not hit:
            continue

        damage = _damage_amount_for_attack(attack, target)
        applied_damage = _apply_damage(target, damage)
        applicable_effects = _filter_applicable_status_effects(target, attack.applied_status_effects)
        applied_effect_count = _apply_status_effects(target, applicable_effects)

        events.append({
            "type": EventType.DAMAGE_APPLIED.value,
            "target_instance_id": target_id,
            "amount": applied_damage,
            "source": "attack",
            "source_id": attack.id,
        })
        if applied_effect_count > 0:
            events.append({
                "type": EventType.STATUS_EFFECT_APPLIED.value,
                "target_instance_id": target_id,
                "count": applied_effect_count,
                "source": "attack",
                "source_id": attack.id,
            })
        if target.hp <= 0:
            events.append({
                "type": EventType.DEATH.value,
                "target_instance_id": target_id,
            })

        state_changes["actors"][target_id] = {
            "hp": target.hp,
            "active_status_effect_count": len(target.active_status_effects),
        }

    return ActionResult.success(events=events, state_changes=state_changes)


def resolve_cast_spell_action(session: "GameSession", encounter: EncounterInstance, action: Action) -> ActionResult:
    actor = _find_actor_by_instance_id(session, encounter, action.actor_instance_id)
    if actor is None:
        return ActionResult.failure(errors=["Spell actor is not part of the active encounter."])
    if getattr(actor, "hp", 0) <= 0:
        return ActionResult.failure(errors=["Dead actors cannot cast spells."])
    if _has_control_effect(actor, ControlType.SILENCED):
        return ActionResult.failure(errors=["Silenced actors cannot cast spells."])

    spell_id = str(action.parameters.get("spell_id", ""))
    spell = _find_spell(actor, spell_id)
    if spell is None:
        return ActionResult.failure(errors=[f"Spell '{spell_id}' is not known by actor '{action.actor_instance_id}'."])
    if actor.spell_slots < spell.spell_cost:
        return ActionResult.failure(errors=["Not enough spell slots to cast this spell."])

    targets, errors = _target_list_for_action(
        session=session,
        encounter=encounter,
        raw_target_ids=action.parameters.get("target_instance_ids", []),
        is_aoe=_is_aoe_spell(spell.type),
    )
    if errors:
        return ActionResult.failure(errors=errors)

    actor.spell_slots -= spell.spell_cost
    events = [{
        "type": EventType.SPELL_CAST.value,
        "actor_instance_id": action.actor_instance_id,
        "spell_id": spell.id,
        "target_instance_ids": [_instance_id(target) for target in targets],
        "spell_cost": spell.spell_cost,
    }]
    state_changes = {
        "actors": {
            _instance_id(actor): {"spell_slots": actor.spell_slots},
        }
    }

    for target in targets:
        target_id = _instance_id(target)

        if _is_heal_spell(spell.type):
            healed_amount = _apply_heal(target, _heal_amount_for_spell(spell))
            events.append({
                "type": EventType.HEALING_APPLIED.value,
                "target_instance_id": target_id,
                "amount": healed_amount,
                "source": "spell",
                "source_id": spell.id,
            })
        elif _is_cleanse_spell(spell.type):
            removed_count = _cleanse_status_effects(target, spell)
            if removed_count > 0:
                events.append({
                    "type": EventType.STATUS_EFFECT_REMOVED.value,
                    "target_instance_id": target_id,
                    "count": removed_count,
                    "source": "spell",
                    "source_id": spell.id,
                })
        elif _is_status_only_spell(spell.type):
            applicable_effects = _filter_applicable_status_effects(target, spell.applied_status_effects)
            applied_effect_count = _apply_status_effects(target, applicable_effects)
            if applied_effect_count > 0:
                events.append({
                    "type": EventType.STATUS_EFFECT_APPLIED.value,
                    "target_instance_id": target_id,
                    "count": applied_effect_count,
                    "source": "spell",
                    "source_id": spell.id,
                })
        else:
            hit, hit_result, roll_events = _resolve_hit_result(
                actor=actor,
                actor_id=action.actor_instance_id,
                target=target,
                target_id=target_id,
                hit_modifiers=spell.hit_modifiers,
                dc=spell.DC,
            )
            events.extend(roll_events)
            events.append({
                "type": EventType.ATTACK_HIT.value if hit else EventType.ATTACK_MISSED.value,
                "actor_instance_id": action.actor_instance_id,
                "target_instance_id": target_id,
                "spell_id": spell.id,
                "hit_result": hit_result,
            })
            if hit:
                damage = _damage_amount_for_spell(spell, target)
                applied_damage = _apply_damage(target, damage)
                events.append({
                    "type": EventType.DAMAGE_APPLIED.value,
                    "target_instance_id": target_id,
                    "amount": applied_damage,
                    "source": "spell",
                    "source_id": spell.id,
                })
                applicable_effects = _filter_applicable_status_effects(target, spell.applied_status_effects)
                applied_effect_count = _apply_status_effects(target, applicable_effects)
                if applied_effect_count > 0:
                    events.append({
                        "type": EventType.STATUS_EFFECT_APPLIED.value,
                        "target_instance_id": target_id,
                        "count": applied_effect_count,
                        "source": "spell",
                        "source_id": spell.id,
                    })
                if target.hp <= 0:
                    events.append({
                        "type": EventType.DEATH.value,
                        "target_instance_id": target_id,
                    })

        state_changes["actors"][target_id] = {
            "hp": target.hp,
            "active_status_effect_count": len(target.active_status_effects),
        }

    return ActionResult.success(events=events, state_changes=state_changes)