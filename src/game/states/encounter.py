from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

from game.core.action import Action, validate_action
from game.core.action_result import ActionResult
from game.core.enums import ActionType, EventType
from game.combat.initiative import initiate_encounter
from game.combat.resolution import calculate_damage_multiplier, resolve_attack_action, resolve_cast_spell_action
from game.combat.status_effect import merged_damage_affinities_from_effects, tick_and_prune_status_effects
from game.enums import ControlType, DamageType, GameState, StatusEffectType
from game.runtime.models import EncounterInstance

if TYPE_CHECKING:
    from game.states.game_session import GameSession

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

    # properties of encounter

    def start_encounter(self, session: "GameSession", encounter: EncounterInstance) -> ActionResult:
        if encounter is None:
            return ActionResult.failure(errors=["Encounter cannot be None."])

        for index, enemy in enumerate(encounter.enemies, start=1):
            enemy.enemy_instance_id = f"enemy_{index}"

        self.current_encounter = encounter
        self.turn_order = initiate_encounter(session, encounter)
        self.current_turn_index = 0
        return self._transition(session, GameState.ENCOUNTER)

    def handle_attack(self, session: "GameSession", action: Action) -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to handle attack."])
        if action.type is not ActionType.ATTACK:
            return ActionResult.failure(errors=["Invalid action type for attack handler."])
        validation_result = self._validate_action_turn_owner(action)
        if validation_result.errors:
            return validation_result
        return resolve_attack_action(session, self.current_encounter, action)

    def handle_cast_spell(self, session: "GameSession", action: Action) -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to handle spell cast."])
        if action.type is not ActionType.CAST_SPELL:
            return ActionResult.failure(errors=["Invalid action type for cast spell handler."])
        validation_result = self._validate_action_turn_owner(action)
        if validation_result.errors:
            return validation_result
        return resolve_cast_spell_action(session, self.current_encounter, action)

    def handle_end_turn(self, session: "GameSession", action: Action | None = None) -> ActionResult:
        if action is not None:
            if action.type is not ActionType.END_TURN:
                return ActionResult.failure(errors=["Invalid action type for end turn handler."])
            validation_result = self._validate_action_turn_owner(action)
            if validation_result.errors:
                return validation_result
        return self.advance_turn(session)

    def handle_action(self, session: "GameSession", action: Action) -> ActionResult:
        if action.type not in self.SUPPORTED_ACTIONS:
            return self._unsupported_action(action)

        if action.type is ActionType.ATTACK:
            return self.handle_attack(session, action)
        if action.type is ActionType.CAST_SPELL:
            return self.handle_cast_spell(session, action)
        if action.type is ActionType.END_TURN:
            return self.handle_end_turn(session, action)
        return self._unsupported_action(action)

    @staticmethod
    def _instance_id(actor: Any) -> str:
        return str(getattr(actor, "player_instance_id", "") or getattr(actor, "enemy_instance_id", ""))

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
            if effect_instance.status_effect.type is not StatusEffectType.CONTROL:
                continue
            if effect_instance.status_effect.control_type in {ControlType.STUNNED, ControlType.ASLEEP}:
                return True
        return False

    def _apply_global_turn_ticks(self, session: "GameSession") -> tuple[List[dict], Dict[str, Any]]:
        events: List[dict] = []
        state_changes: Dict[str, Any] = {"actors": {}}

        for actor in [item for item in self._all_actors(session) if getattr(item, "hp", 0) > 0]:
            actor_id = self._instance_id(actor)
            dot_tick_count = 0
            hot_tick_count = 0

            for effect_instance in list(getattr(actor, "active_status_effects", [])):
                if effect_instance.duration <= 0:
                    continue

                status_effect = effect_instance.status_effect
                if status_effect.type is StatusEffectType.DOT:
                    dot_tick_count += 1
                    damage_type = status_effect.damage_types[0] if status_effect.damage_types else DamageType.FORCE
                    extra_immunities, extra_resistances, extra_vulnerabilities = merged_damage_affinities_from_effects(
                        getattr(actor, "active_status_effects", [])
                    )
                    multiplier = calculate_damage_multiplier(
                        damage_type,
                        sorted(list(set(actor.merged_immunities + extra_immunities)), key=lambda x: x.value),
                        sorted(list(set(actor.merged_resistances + extra_resistances)), key=lambda x: x.value),
                        sorted(list(set(actor.merged_vulnerabilities + extra_vulnerabilities)), key=lambda x: x.value),
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
                elif status_effect.type is StatusEffectType.HOT:
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
            if hasattr(session, "transition_to"):
                return session.transition_to(GameState.POSTGAME)
            session.state = GameState.POSTGAME
            return ActionResult.success(state_changes={"state": {"to": GameState.POSTGAME.value}})

        events: List[dict] = [{"type": EventType.TURN_ENDED.value, "actor_instance_id": self._current_actor_instance_id()}]

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
                    }
                )
                continue
            if self._has_skip_control(next_actor):
                events.append(
                    {
                        "type": EventType.TURN_SKIPPED.value,
                        "actor_instance_id": next_actor_id,
                        "reason": "control",
                    }
                )
                continue

            selected_index = next_index
            break

        tick_events, tick_changes = self._apply_global_turn_ticks(session)
        events.extend(tick_events)

        if selected_index is not None:
            self.current_turn_index = selected_index
            current_actor = self._find_actor(session, self.turn_order[self.current_turn_index])
            turn_started_event = {
                "type": EventType.TURN_STARTED.value,
                "actor_instance_id": self.turn_order[self.current_turn_index],
            }
            persona = getattr(current_actor, "persona", "") if current_actor is not None else ""
            if persona:
                turn_started_event["persona"] = str(persona)
            events.append(
                turn_started_event
            )

        return ActionResult.success(events=events, state_changes=tick_changes)

    def end_encounter(self, session: "GameSession") -> ActionResult:
        if self.current_encounter is None:
            return ActionResult.failure(errors=["No active encounter to end."])

        encounter_id = self.current_encounter.id
        clear_reward = int(getattr(self.current_encounter, "clear_reward", 0))
        session.points = int(getattr(session, "points", 0)) + clear_reward
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


    # serialize and deserialize functions