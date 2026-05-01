from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any, Dict, List

from game.core.action import Action, validate_action
from game.core.action_result import ActionResult
from game.core.enums import ActionType, EventType
from game.combat.initiative import roll_initiative_rows
from game.combat.resolution import calculate_damage_multiplier, resolve_attack_action, resolve_cast_spell_action
from game.combat.status_effect import merged_damage_affinities_from_effects, tick_and_prune_status_effects
from game.enums import ControlType, DamageType, GameState, StatusEffectType
from game.runtime.models import EncounterInstance

if TYPE_CHECKING:
    from game.states.game_session import GameSession


logger = logging.getLogger(__name__)

@dataclass
class EncounterState:
    current_encounter: EncounterInstance | None = None
    turn_order: List[str] = field(default_factory=list)  # actor instance ids
    current_turn_index: int = 0
    post_encounter_summary: Dict[str, Any] = field(default_factory=dict)
    SUPPORTED_ACTIONS = {
        ActionType.ATTACK,
        ActionType.CAST_SPELL,
        ActionType.END_TURN,
    }

    @staticmethod
    def _unsupported_action(action: Action) -> ActionResult:
        return ActionResult.failure(errors=[f"Unsupported encounter action type: '{action.type.value}'."])

    @staticmethod
    def _merge_state_changes(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        def _deep_merge(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> Dict[str, Any]:
            merged: Dict[str, Any] = dict(lhs)
            for key, value in dict(rhs).items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = _deep_merge(dict(merged[key]), dict(value))
                else:
                    merged[key] = value
            return merged

        return _deep_merge(dict(base), dict(extra))

    @staticmethod
    def _transition(session: "GameSession", target_state: GameState) -> ActionResult:
        if hasattr(session, "transition_to"):
            transition_result = session.transition_to(target_state)
            if isinstance(transition_result, ActionResult):
                return transition_result
            return ActionResult.failure(errors=["Session transition_to returned an invalid result type."])
        session.state = target_state
        return ActionResult.success(
            state_changes={"state": {"to": target_state.value}}
        )

    def _current_actor_instance_id(self) -> str:
        if not self.turn_order:
            return ""
        if self.current_turn_index < 0 or self.current_turn_index >= len(self.turn_order):
            return ""
        return self.turn_order[self.current_turn_index]

    def _validate_action_turn_owner(self, action: Action) -> ActionResult:
        errors = validate_action(action)
        if errors:
            return ActionResult.failure(errors=errors)
        current_actor = self._current_actor_instance_id()
        if not current_actor:
            return ActionResult.failure(errors=["Current turn actor is not available."])
        if action.actor_instance_id != current_actor:
            return ActionResult.failure(
                errors=[f"Action actor '{action.actor_instance_id}' is invalid for current turn; expected '{current_actor}'."]
            )
        return ActionResult.success()

    def start_encounter(self, session: "GameSession", encounter: EncounterInstance) -> ActionResult:
        if encounter is None:
            return ActionResult.failure(errors=["Encounter cannot be None."])

        for index, enemy in enumerate(encounter.enemies, start=1):
            enemy.enemy_instance_id = f"enemy_{index}"

        self.current_encounter = encounter
        initiative_rows = roll_initiative_rows(session, encounter)
        self.turn_order = [str(row["actor_instance_id"]) for row in initiative_rows]
        self.current_turn_index = 0
        transition_result = self._transition(session, GameState.ENCOUNTER)
        if transition_result.errors:
            return transition_result

        dice_events: List[dict] = []
        for row in initiative_rows:
            actor_instance_id = str(row["actor_instance_id"])
            roll = int(row["roll"])
            modifier = int(row["modifier"])
            total = int(row["initiative"])
            dice_events.extend(
                [
                    {
                        "type": EventType.DICE_ROLLED.value,
                        "roll_context": "initiative",
                        "actor_instance_id": actor_instance_id,
                        "notation": "1d20",
                        "roll": roll,
                    },
                    {
                        "type": EventType.DICE_RESULT.value,
                        "roll_context": "initiative",
                        "actor_instance_id": actor_instance_id,
                        "base_roll": roll,
                        "modifier": modifier,
                        "total": total,
                    },
                ]
            )

        events = [
            *transition_result.events,
            {
                "type": EventType.INITIATIVE_ROLLED.value,
                "encounter_id": encounter.id,
                "initiative_rows": [dict(row) for row in initiative_rows],
                "turn_order": list(self.turn_order),
                "turn_index": self.current_turn_index,
            },
            *dice_events,
            {
                "type": EventType.INITIATIVE_RESULT.value,
                "encounter_id": encounter.id,
                "turn_order": list(self.turn_order),
                "current_actor_instance_id": self._current_actor_instance_id(),
                "turn_index": self.current_turn_index,
            },
            {
                "type": EventType.ENCOUNTER_STARTED.value,
                "encounter_id": encounter.id,
                "encounter_name": str(getattr(encounter, "name", "")),
                "enemy_ids": [str(getattr(enemy, "enemy_instance_id", "")) for enemy in list(encounter.enemies)],
                "turn_order": list(self.turn_order),
                "turn_index": self.current_turn_index,
            },
        ]
        current_actor_id = self._current_actor_instance_id()
        if current_actor_id:
            events.append(
                {
                    "type": EventType.TURN_STARTED.value,
                    "actor_instance_id": current_actor_id,
                    "turn_index": self.current_turn_index,
                }
            )
        return ActionResult.success(events=events, state_changes=dict(transition_result.state_changes))

    def handle_attack(self, session: "GameSession", action: Action) -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to handle attack."])
        if action.type != ActionType.ATTACK:
            return ActionResult.failure(errors=["Invalid action type for attack handler."])
        validation_result = self._validate_action_turn_owner(action)
        if validation_result.errors:
            return validation_result
        return resolve_attack_action(session, self.current_encounter, action)

    def handle_cast_spell(self, session: "GameSession", action: Action) -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to handle spell cast."])
        if action.type != ActionType.CAST_SPELL:
            return ActionResult.failure(errors=["Invalid action type for cast spell handler."])
        validation_result = self._validate_action_turn_owner(action)
        if validation_result.errors:
            return validation_result
        return resolve_cast_spell_action(session, self.current_encounter, action)

    def handle_end_turn(self, session: "GameSession", action: Action | None = None) -> ActionResult:
        if action is not None:
            if action.type != ActionType.END_TURN:
                return ActionResult.failure(errors=["Invalid action type for end turn handler."])
            validation_result = self._validate_action_turn_owner(action)
            if validation_result.errors:
                return validation_result
        return self.advance_turn(session)

    def handle_action(self, session: "GameSession", action: Action) -> ActionResult:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        if action.type == ActionType.ATTACK:
            result = self.handle_attack(session, action)
            if result.errors:
                return result
            turn_result = self.advance_turn(session)
            if turn_result.errors:
                return turn_result
            return ActionResult.success(
                events=[*result.events, *turn_result.events],
                state_changes=self._merge_state_changes(result.state_changes, turn_result.state_changes),
            )
        if action.type == ActionType.CAST_SPELL:
            result = self.handle_cast_spell(session, action)
            if result.errors:
                return result
            turn_result = self.advance_turn(session)
            if turn_result.errors:
                return turn_result
            return ActionResult.success(
                events=[*result.events, *turn_result.events],
                state_changes=self._merge_state_changes(result.state_changes, turn_result.state_changes),
            )
        if action.type == ActionType.END_TURN:
            return self.handle_end_turn(session, action)
        return self._unsupported_action(action)

    def _instance_id(self, actor: Any) -> str:
        actor_instance_id = str(getattr(actor, "player_instance_id", "") or getattr(actor, "enemy_instance_id", ""))
        if not actor_instance_id:
            logger.warning(
                "Encounter actor is missing instance id.",
                extra={
                    "actor_class": actor.__class__.__name__,
                    "actor_name": str(getattr(actor, "name", "")),
                    "encounter_id": str(getattr(self.current_encounter, "id", "")),
                },
            )
        return actor_instance_id

    def _all_actors(self, session: "GameSession") -> List[Any]:
        if self.current_encounter is None:
            return list(session.party)
        return [*session.party, *self.current_encounter.enemies]

    def _find_actor(self, session: "GameSession", actor_instance_id: str) -> Any | None:
        for actor in self._all_actors(session):
            if self._instance_id(actor) == actor_instance_id:
                return actor
        return None

    @staticmethod
    def _has_skip_control(actor: Any) -> bool:
        for effect_instance in getattr(actor, "active_status_effects", []):
            if effect_instance.duration <= 0:
                continue
            if effect_instance.status_effect.type != StatusEffectType.CONTROL:
                continue
            if effect_instance.status_effect.control_type in {ControlType.STUNNED, ControlType.ASLEEP}:
                return True
        return False

    def _apply_global_turn_ticks(self, session: "GameSession") -> tuple[List[dict], Dict[str, Any]]:
        events: List[dict] = []
        state_changes: Dict[str, Any] = {"actors": {}}

        for actor in [item for item in self._all_actors(session) if getattr(item, "hp", 0) > 0]:
            actor_id = self._instance_id(actor)
            if not actor_id:
                continue
            dot_tick_count = 0
            hot_tick_count = 0

            for effect_instance in list(getattr(actor, "active_status_effects", [])):
                if effect_instance.duration <= 0:
                    continue

                status_effect = effect_instance.status_effect
                if status_effect.type == StatusEffectType.DOT:
                    dot_tick_count += 1
                    damage_type = status_effect.damage_types[0] if status_effect.damage_types else DamageType.FORCE
                    extra_immunities, extra_resistances, extra_vulnerabilities = merged_damage_affinities_from_effects(
                        getattr(actor, "active_status_effects", [])
                    )
                    actor_immunities = list(getattr(actor, "merged_immunities", []) or [])
                    actor_resistances = list(getattr(actor, "merged_resistances", []) or [])
                    actor_vulnerabilities = list(getattr(actor, "merged_vulnerabilities", []) or [])
                    multiplier = calculate_damage_multiplier(
                        damage_type,
                        sorted(list(set(actor_immunities + extra_immunities)), key=lambda x: x.value),
                        sorted(list(set(actor_resistances + extra_resistances)), key=lambda x: x.value),
                        sorted(list(set(actor_vulnerabilities + extra_vulnerabilities)), key=lambda x: x.value),
                    )
                    amount = max(0, int(status_effect.damage_value * multiplier))
                    before = actor.hp
                    actor.hp = max(0, actor.hp - amount)
                    events.append(
                        {
                            "type": EventType.DAMAGE_APPLIED.value,
                            "target_instance_id": actor_id,
                            "amount": before - actor.hp,
                            "source": "status_effect",
                            "source_id": status_effect.id,
                        }
                    )
                elif status_effect.type == StatusEffectType.HOT:
                    hot_tick_count += 1
                    before = actor.hp
                    actor.hp = min(getattr(actor, "max_hp", actor.hp), actor.hp + max(0, status_effect.heal_value))
                    events.append(
                        {
                            "type": EventType.HEALING_APPLIED.value,
                            "target_instance_id": actor_id,
                            "amount": actor.hp - before,
                            "source": "status_effect",
                            "source_id": status_effect.id,
                        }
                    )

            removed_count = tick_and_prune_status_effects(getattr(actor, "active_status_effects", []))
            if dot_tick_count + hot_tick_count > 0:
                events.append(
                    {
                        "type": EventType.STATUS_EFFECT_TICKED.value,
                        "target_instance_id": actor_id,
                        "count": dot_tick_count + hot_tick_count,
                    }
                )
            if removed_count > 0:
                events.append(
                    {
                        "type": EventType.STATUS_EFFECT_REMOVED.value,
                        "target_instance_id": actor_id,
                        "count": removed_count,
                        "source": "turn_tick",
                    }
                )
            if actor.hp <= 0:
                events.append({"type": EventType.DEATH.value, "target_instance_id": actor_id})

            state_changes["actors"][actor_id] = {
                "hp": actor.hp,
                "active_status_effect_count": len(getattr(actor, "active_status_effects", [])),
            }

        return events, state_changes

    def advance_turn(self, session: "GameSession") -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to advance turn."])
        if not self.turn_order:
            return ActionResult.failure(errors=["Cannot advance turn because turn order is empty."])

        alive_players = [player for player in session.party if player.hp > 0]
        alive_enemies = [enemy for enemy in self.current_encounter.enemies if enemy.hp > 0]
        if not alive_enemies:
            return self.end_encounter(session)
        if not alive_players:
            return self._transition(session, GameState.POSTGAME)

        events: List[dict] = []
        ended_actor_id = self._current_actor_instance_id()
        if ended_actor_id:
            events.append(
                {
                    "type": EventType.TURN_ENDED.value,
                    "actor_instance_id": ended_actor_id,
                    "turn_index": self.current_turn_index,
                }
            )

        checked = 0
        next_index = self.current_turn_index
        selected_index: int | None = None
        while checked < len(self.turn_order):
            next_index = (next_index + 1) % len(self.turn_order)
            checked += 1
            next_actor_id = self.turn_order[next_index]
            next_actor = self._find_actor(session, next_actor_id)
            if next_actor is None or getattr(next_actor, "hp", 0) <= 0:
                events.append(
                    {
                        "type": EventType.TURN_SKIPPED.value,
                        "actor_instance_id": next_actor_id,
                        "reason": "dead_or_missing",
                        "turn_index": next_index,
                    }
                )
                continue
            if self._has_skip_control(next_actor):
                events.append(
                    {
                        "type": EventType.TURN_SKIPPED.value,
                        "actor_instance_id": next_actor_id,
                        "reason": "control",
                        "turn_index": next_index,
                    }
                )
                continue

            selected_index = next_index
            break

        tick_events, tick_changes = self._apply_global_turn_ticks(session)
        events.extend(tick_events)

        if selected_index is None:
            fallback_index = (self.current_turn_index + 1) % len(self.turn_order)
            fallback_actor_id = str(self.turn_order[fallback_index])
            events.append(
                {
                    "type": EventType.TURN_SKIPPED.value,
                    "actor_instance_id": fallback_actor_id,
                    "reason": "no_eligible_actor_cycle",
                    "turn_index": fallback_index,
                }
            )
            selected_index = fallback_index

        self.current_turn_index = selected_index
        current_actor = self._find_actor(session, self.turn_order[self.current_turn_index])
        turn_started_event = {
            "type": EventType.TURN_STARTED.value,
            "actor_instance_id": self.turn_order[self.current_turn_index],
            "turn_index": self.current_turn_index,
        }
        persona = getattr(current_actor, "persona", "") if current_actor is not None else ""
        if persona:
            turn_started_event["persona"] = str(persona)
        events.append(turn_started_event)

        return ActionResult.success(events=events, state_changes=tick_changes)

    def end_encounter(self, session: "GameSession") -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to end."])

        encounter_id = self.current_encounter.id
        clear_reward = int(getattr(self.current_encounter, "clear_reward", 0))
        session.points = int(getattr(session, "points", 0)) + clear_reward
        # run a check function to see if all encounters in the room are cleared
        self.current_encounter.cleared = True

        status_cleared_events: List[dict] = []
        for player in getattr(session, "party", []):
            active_status_effects = getattr(player, "active_status_effects", None)
            if not isinstance(active_status_effects, list):
                continue
            removed_count = len(active_status_effects)
            if removed_count <= 0:
                continue
            active_status_effects.clear()
            status_cleared_events.append(
                {
                    "type": EventType.STATUS_EFFECT_REMOVED.value,
                    "target_instance_id": self._instance_id(player),
                    "count": removed_count,
                    "source": "encounter_end",
                }
            )

        self.post_encounter_summary = {
            "encounter_id": encounter_id,
            "status": "cleared",
            "clear_reward": clear_reward,
            "session_points": session.points,
        }
        self.current_encounter = None
        self.turn_order = []
        self.current_turn_index = 0

        room_cleared_event: dict | None = None
        current_room = getattr(getattr(session, "exploration", None), "current_room", None)
        if current_room is not None:
            room_encounters = list(getattr(current_room, "encounters", []) or [])
            current_room.is_cleared = all(bool(getattr(room_encounter, "cleared", False)) for room_encounter in room_encounters)
            if current_room.is_cleared:
                room_cleared_event = {
                    "type": EventType.ROOM_CLEARED.value,
                    "room_id": str(getattr(current_room, "id", "")),
                    "room_name": str(getattr(current_room, "name", "")),
                }

        transition_result = self._transition(session, GameState.EXPLORATION)
        if transition_result.errors:
            return transition_result

        merged_state_changes = dict(transition_result.state_changes)
        merged_state_changes["encounter"] = dict(self.post_encounter_summary)
        return ActionResult.success(
            events=[
                {
                    "type": EventType.REWARD_GRANTED.value,
                    "encounter_id": encounter_id,
                    "amount": clear_reward,
                    "session_points": session.points,
                },
                *status_cleared_events,
                *([room_cleared_event] if room_cleared_event is not None else []),
                {
                    "type": EventType.ENCOUNTER_ENDED.value,
                    "encounter_id": encounter_id,
                },
            ],
            state_changes=merged_state_changes,
        )

    def to_dict(self) -> dict:
        return {
            "current_encounter_id": self.current_encounter.id if self.current_encounter else "",
            "turn_order": list(self.turn_order),
            "current_turn_index": self.current_turn_index,
            "post_encounter_summary": dict(self.post_encounter_summary),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterState":
        turn_order = data.get("turn_order", [])
        if not isinstance(turn_order, list):
            turn_order = []
        summary = data.get("post_encounter_summary", {})
        if not isinstance(summary, dict):
            summary = {}
        return cls(
            current_encounter=None,
            turn_order=[str(item) for item in turn_order],
            current_turn_index=int(data.get("current_turn_index", 0)),
            post_encounter_summary=summary,
        )