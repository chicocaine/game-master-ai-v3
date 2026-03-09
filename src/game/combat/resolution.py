from __future__ import annotations


import math
from typing import Any, List

from core.action import Action
from core.action_result import ActionResult
from core.enums import EventType

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

from typing import TYPE_CHECKING

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
        if status_effect.type is StatusEffectType.CONTROL and status_effect.control_type is control_type:
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
    if effect.type is not StatusEffectType.CONTROL:
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
            status_effect.type is StatusEffectType.CONTROL
            and status_effect.control_type in cleanse_control_types
        ):
            return True
        return False

    if not cleanse_types and not cleanse_control_types:
        remaining = [
            effect for effect in active_effects
            if effect.status_effect.type is not StatusEffectType.CONTROL
        ]
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

def _damage_amount_for_attack(attack, target) -> int:
    raw_damage = roll_dice(attack.damage_roll)
    base_damage = max(0, raw_damage)
    damage_types = attack.damage_types or [DamageType.FORCE]
    primary_damage_type = damage_types[0]
    extra_immunities, extra_resistances, extra_vulnerabilities = merged_damage_affinities_from_effects(
        getattr(target, "active_status_effects", [])
    )
    multiplier = calculate_damage_multiplier(
        primary_damage_type,
        sorted(list(set(target.merged_immunities + extra_immunities)), key=lambda x: x.value),
        sorted(list(set(target.merged_resistances + extra_resistances)), key=lambda x: x.value),
        sorted(list(set(target.merged_vulnerabilities + extra_vulnerabilities)), key=lambda x: x.value),
    )
    return max(0, math.floor(base_damage * multiplier))


def _damage_amount_for_spell(spell, target) -> int:
    raw_damage = roll_dice(spell.damage_roll)
    base_damage = max(0, raw_damage)
    damage_types = spell.damage_types or [DamageType.FORCE]
    primary_damage_type = damage_types[0]
    extra_immunities, extra_resistances, extra_vulnerabilities = merged_damage_affinities_from_effects(
        getattr(target, "active_status_effects", [])
    )
    multiplier = calculate_damage_multiplier(
        primary_damage_type,
        sorted(list(set(target.merged_immunities + extra_immunities)), key=lambda x: x.value),
        sorted(list(set(target.merged_resistances + extra_resistances)), key=lambda x: x.value),
        sorted(list(set(target.merged_vulnerabilities + extra_vulnerabilities)), key=lambda x: x.value),
    )
    return max(0, math.floor(base_damage * multiplier))

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


def _did_hit_target(actor: Any, target: Any, hit_modifiers: int, dc: int) -> bool:
    actor_effect_attack_modifier = total_attack_modifier_from_effects(
        getattr(actor, "active_status_effects", [])
    )
    target_effect_ac_modifier = total_ac_modifier_from_effects(
        getattr(target, "active_status_effects", [])
    )
    effective_target_ac = max(0, getattr(target, "effective_ac", 0) + target_effect_ac_modifier)

    if dc > 0:
        return roll_save_throw() + getattr(target, "initiative_mod", 0) < dc
    return (
        roll_save_throw()
        + hit_modifiers
        + getattr(actor, "merged_attack_modifier", 0)
        + actor_effect_attack_modifier
        >= effective_target_ac
    )


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
        hit = _did_hit_target(actor, target, attack.hit_modifiers, attack.DC)
        events.append({
            "type": EventType.ATTACK_HIT.value if hit else EventType.ATTACK_MISSED.value,
            "actor_instance_id": action.actor_instance_id,
            "target_instance_id": target_id,
            "attack_id": attack.id,
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
            hit = _did_hit_target(actor, target, spell.hit_modifiers, spell.DC)
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