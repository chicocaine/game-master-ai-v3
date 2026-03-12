import json
from collections import deque
from dataclasses import dataclass, field
import time
from typing import Any, Deque, Dict, Optional

from game.core.action import Action, create_action
from game.core.enums import ActionType

from game.engine.interfaces import ActionProvider, EngineContext
from game.enums import GameState
from game.llm.client import RetryPolicy, invoke_with_retry
from game.llm.config import LlmSettings
from game.llm.context_builder import build_context_envelope
from game.llm.context_window import fit_dict_to_token_budget
from game.llm.contracts import LlmMessage, LlmRequest
from game.llm.debug_context import emit_context
from game.llm.errors import LlmError, LlmRetryExhaustedError
from game.llm.fewshot import get_few_shot_examples_with_budget
from game.llm.json_parse import parse_json_object, validate_action_payload
from game.llm.prompts import enemy_ai
from game.llm.telemetry import LlmTelemetry


ENEMY_AI_PROMPT_VERSION = "enemy_ai.v2"


@dataclass
class EnemyLlmActionProvider(ActionProvider):
    client: Any
    settings: LlmSettings
    retry_policy: RetryPolicy = field(default_factory=lambda: RetryPolicy(max_attempts=2, backoff_seconds=0.0))
    telemetry: LlmTelemetry | None = None
    include_provider_metadata: bool = True
    timeline: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=40))

    def _append_timeline(self, entry: Dict[str, Any]) -> None:
        self.timeline.append(dict(entry))

    def _current_turn_enemy_id(self, session: Any) -> str:
        if getattr(session, "state", None) is not GameState.ENCOUNTER:
            return ""

        encounter_state = getattr(session, "encounter", None)
        if encounter_state is None:
            return ""

        turn_order = getattr(encounter_state, "turn_order", None)
        turn_index = getattr(encounter_state, "current_turn_index", -1)
        if not isinstance(turn_order, list) or not turn_order:
            return ""
        if not isinstance(turn_index, int) or turn_index < 0 or turn_index >= len(turn_order):
            return ""

        actor_id = str(turn_order[turn_index])
        if actor_id.startswith("enemy_"):
            return actor_id
        return ""

    def _enemy_for_id(self, session: Any, enemy_id: str) -> Any | None:
        encounter_state = getattr(session, "encounter", None)
        current_encounter = getattr(encounter_state, "current_encounter", None) if encounter_state is not None else None
        enemies = getattr(current_encounter, "enemies", []) if current_encounter is not None else []

        for enemy in enemies:
            if str(getattr(enemy, "enemy_instance_id", "")) == enemy_id:
                return enemy
        return None

    def _summarize_combat(self, session: Any, current_enemy_id: str) -> Dict[str, Any]:
        party = getattr(session, "party", [])
        encounter_state = getattr(session, "encounter", None)
        current_encounter = getattr(encounter_state, "current_encounter", None) if encounter_state is not None else None
        enemies = getattr(current_encounter, "enemies", []) if current_encounter is not None else []

        player_targets = []
        for player in party:
            player_id = str(getattr(player, "player_instance_id", ""))
            if not player_id:
                continue
            player_targets.append(
                {
                    "instance_id": player_id,
                    "hp": int(getattr(player, "hp", 0)),
                    "max_hp": int(getattr(player, "max_hp", 0)),
                }
            )

        enemy_status = []
        for enemy in enemies:
            enemy_id = str(getattr(enemy, "enemy_instance_id", ""))
            if not enemy_id:
                continue
            enemy_status.append(
                {
                    "instance_id": enemy_id,
                    "hp": int(getattr(enemy, "hp", 0)),
                    "max_hp": int(getattr(enemy, "max_hp", 0)),
                }
            )

        return {
            "state": GameState.ENCOUNTER.value,
            "current_enemy_id": current_enemy_id,
            "turn_order": list(getattr(encounter_state, "turn_order", [])) if encounter_state is not None else [],
            "current_turn_index": int(getattr(encounter_state, "current_turn_index", 0)) if encounter_state is not None else 0,
            "player_targets": player_targets,
            "enemies": enemy_status,
        }

    @staticmethod
    def _alive_player_target_ids(session: Any) -> list[str]:
        target_ids: list[str] = []
        for player in getattr(session, "party", []):
            if int(getattr(player, "hp", 0)) <= 0:
                continue
            player_id = str(getattr(player, "player_instance_id", ""))
            if player_id:
                target_ids.append(player_id)
        return target_ids

    @staticmethod
    def _attack_ids(enemy: Any) -> list[str]:
        attack_ids: list[str] = []
        for attack in getattr(enemy, "merged_attacks", []):
            attack_id = str(getattr(attack, "id", ""))
            if attack_id:
                attack_ids.append(attack_id)
        return attack_ids

    @staticmethod
    def _spell_choices(enemy: Any) -> list[dict[str, Any]]:
        spell_slots = int(getattr(enemy, "spell_slots", 0))
        spells: list[dict[str, Any]] = []
        for spell in getattr(enemy, "merged_spells", []):
            spell_id = str(getattr(spell, "id", ""))
            if not spell_id:
                continue
            spell_cost = int(getattr(spell, "spell_cost", 0))
            spells.append(
                {
                    "spell_id": spell_id,
                    "spell_cost": spell_cost,
                    "is_castable": spell_slots >= spell_cost,
                }
            )
        return spells

    def _build_legal_action_space(self, session: Any, enemy: Any) -> Dict[str, Any]:
        target_ids = self._alive_player_target_ids(session)
        spell_choices = self._spell_choices(enemy)
        return {
            "attack_ids": self._attack_ids(enemy),
            "spell_choices": spell_choices,
            "target_instance_ids": target_ids,
            "can_end_turn": True,
        }

    def _fallback_action(self, enemy_id: str, reason: str, legal_action_space: Dict[str, Any]) -> Action:
        if self.telemetry is not None:
            self.telemetry.emit_fallback("enemy_ai", ENEMY_AI_PROMPT_VERSION, reason)
        metadata: Dict[str, Any] = {
            "provider": "enemy_llm",
            "fallback": True,
            "fallback_reason": reason,
        }

        target_ids = [str(item) for item in legal_action_space.get("target_instance_ids", []) if str(item)]
        attack_ids = [str(item) for item in legal_action_space.get("attack_ids", []) if str(item)]
        spell_choices = [
            item for item in legal_action_space.get("spell_choices", [])
            if isinstance(item, dict) and str(item.get("spell_id", ""))
        ]

        if target_ids and attack_ids:
            return create_action(
                action_type=ActionType.ATTACK,
                parameters={
                    "attack_id": attack_ids[0],
                    "target_instance_ids": [target_ids[0]],
                },
                actor_instance_id=enemy_id,
                metadata=metadata,
            )

        castable_spell_id = ""
        for choice in spell_choices:
            if bool(choice.get("is_castable", False)):
                castable_spell_id = str(choice.get("spell_id", ""))
                break
        if target_ids and castable_spell_id:
            return create_action(
                action_type=ActionType.CAST_SPELL,
                parameters={
                    "spell_id": castable_spell_id,
                    "target_instance_ids": [target_ids[0]],
                },
                actor_instance_id=enemy_id,
                metadata=metadata,
            )

        return create_action(
            action_type=ActionType.END_TURN,
            parameters={},
            actor_instance_id=enemy_id,
            metadata=metadata,
        )

    def _recent_decisions_for_prompt(self, max_items: int = 8) -> list[dict[str, Any]]:
        items = list(self.timeline)[-max_items:]
        compact: list[dict[str, Any]] = []
        for item in items:
            entry: dict[str, Any] = {}
            kind = item.get("kind")
            if isinstance(kind, str) and kind:
                entry["kind"] = kind
            action_type = item.get("type")
            if isinstance(action_type, str) and action_type:
                entry["action_type"] = action_type
            parameters = item.get("parameters")
            if isinstance(parameters, dict) and parameters:
                entry["parameters"] = dict(parameters)
            fallback_reason = item.get("fallback_reason")
            if isinstance(fallback_reason, str) and fallback_reason:
                entry["fallback_reason"] = fallback_reason
            if entry:
                compact.append(entry)
        return compact

    def _build_request(
        self,
        enemy_id: str,
        enemy_persona: str,
        combat_summary: Dict[str, Any],
        legal_action_space: Dict[str, Any],
        step_count: int | None = None,
    ) -> LlmRequest:
        compact_summary = fit_dict_to_token_budget(
            combat_summary,
            max_tokens=max(96, self.settings.enemy.max_tokens // 2),
            priority_keys=["state", "current_enemy_id", "current_turn_index", "turn_order", "player_targets", "enemies"],
        )
        context_envelope = build_context_envelope(
            current_context=compact_summary,
            allowed_actions=["attack", "cast_spell", "end_turn"],
            actor_context={
                "actor_instance_id": enemy_id,
                "source": "enemy_ai",
                "enemy_persona": enemy_persona,
                "legal_action_space": dict(legal_action_space),
            },
            timeline_entries=list(self.timeline),
            max_timeline_items=10,
            max_timeline_tokens=max(64, self.settings.enemy.max_tokens // 3),
        )
        payload = enemy_ai.build_user_payload(
            actor_instance_id=enemy_id,
            enemy_persona=enemy_persona,
            combat_summary=compact_summary,
            legal_action_space=legal_action_space,
            recent_decisions=self._recent_decisions_for_prompt(max_items=8),
        )
        schema = enemy_ai.build_response_schema()
        examples = get_few_shot_examples_with_budget(
            domain="enemy_ai",
            max_examples=4,
            max_tokens=max(64, self.settings.enemy.max_tokens // 4),
        )

        emit_context(
            domain="enemy_ai",
            prompt_version=ENEMY_AI_PROMPT_VERSION,
            step_count=step_count,
            state_summary=compact_summary,
            context_envelope=context_envelope,
            few_shot_examples=examples,
        )

        return LlmRequest(
            model=self.settings.model,
            messages=[
                LlmMessage(role="system", content=enemy_ai.system_instructions()),
                LlmMessage(role="system", content=json.dumps({"few_shot_examples": examples})),
                LlmMessage(role="user", content=json.dumps(payload)),
            ],
            temperature=self.settings.enemy.temperature,
            max_tokens=self.settings.enemy.max_tokens,
            timeout_seconds=self.settings.timeout_seconds,
            response_format={"type": "json_schema", "json_schema": schema},
            metadata={
                "provider": "enemy_llm",
                "state": GameState.ENCOUNTER.value,
                "actor_instance_id": enemy_id,
                "prompt_version": ENEMY_AI_PROMPT_VERSION,
            },
        )

    def _action_from_payload(self, payload: Dict[str, Any], enemy_id: str) -> Action:
        validated = validate_action_payload(payload)
        action_data = {
            "type": validated["type"],
            "parameters": validated["parameters"],
            "actor_instance_id": validated["actor_instance_id"] or enemy_id,
            "reasoning": validated["reasoning"],
            "metadata": validated["metadata"],
        }

        if self.include_provider_metadata:
            metadata = dict(action_data.get("metadata", {}))
            metadata["provider"] = "enemy_llm"
            action_data["metadata"] = metadata

        return Action.from_dict(action_data)

    @staticmethod
    def _is_allowed_enemy_action(action: Action) -> bool:
        return action.type in {ActionType.ATTACK, ActionType.CAST_SPELL, ActionType.END_TURN}

    @staticmethod
    def _validate_combat_targets(action: Action) -> bool:
        if action.type in {ActionType.ATTACK, ActionType.CAST_SPELL}:
            targets = action.parameters.get("target_instance_ids")
            if isinstance(targets, str):
                return bool(targets.strip())
            if isinstance(targets, list):
                if not targets:
                    return False
                return all(isinstance(target, str) and bool(target.strip()) for target in targets)
            return False
        return True

    @staticmethod
    def _is_legal_enemy_selection(action: Action, legal_action_space: Dict[str, Any]) -> tuple[bool, str]:
        legal_attack_ids = {str(item) for item in legal_action_space.get("attack_ids", []) if str(item)}
        legal_spell_ids = {
            str(item.get("spell_id"))
            for item in legal_action_space.get("spell_choices", [])
            if isinstance(item, dict) and str(item.get("spell_id", ""))
        }
        legal_target_ids = {str(item) for item in legal_action_space.get("target_instance_ids", []) if str(item)}

        if action.type is ActionType.ATTACK:
            attack_id = str(action.parameters.get("attack_id", ""))
            if attack_id not in legal_attack_ids:
                return False, "invalid_attack_id"
        if action.type is ActionType.CAST_SPELL:
            spell_id = str(action.parameters.get("spell_id", ""))
            if spell_id not in legal_spell_ids:
                return False, "invalid_spell_id"

        if action.type in {ActionType.ATTACK, ActionType.CAST_SPELL}:
            targets = action.parameters.get("target_instance_ids", [])
            if isinstance(targets, str):
                targets = [targets]
            if not isinstance(targets, list):
                return False, "invalid_target_payload"
            for target_id in targets:
                if str(target_id) not in legal_target_ids:
                    return False, "invalid_target_id"

        return True, ""

    def next_action(self, session: Any, ctx: EngineContext) -> Optional[Action]:
        enemy_id = self._current_turn_enemy_id(session)
        if not enemy_id:
            return None

        enemy = self._enemy_for_id(session, enemy_id)
        if enemy is None:
            return None
        enemy_persona = str(getattr(enemy, "persona", "") or "")
        legal_action_space = self._build_legal_action_space(session, enemy)
        combat_summary = self._summarize_combat(session, current_enemy_id=enemy_id)
        combat_summary["legal_action_space"] = dict(legal_action_space)
        step_count = int(getattr(ctx, "step_count", 0))
        self._append_timeline(
            {
                "kind": "enemy_turn",
                "step_count": step_count,
                "enemy_id": enemy_id,
                "legal_action_space": dict(legal_action_space),
            }
        )
        request = self._build_request(
            enemy_id=enemy_id,
            enemy_persona=enemy_persona,
            combat_summary=combat_summary,
            legal_action_space=legal_action_space,
            step_count=step_count,
        )
        started = time.perf_counter()
        response_text = ""

        try:
            response = invoke_with_retry(client=self.client, request=request, retry_policy=self.retry_policy)
            response_text = response.text
            payload = parse_json_object(response.text)
            action = self._action_from_payload(payload, enemy_id=enemy_id)
        except LlmError as exc:
            error_msg = str(exc.last_error) if isinstance(exc, LlmRetryExhaustedError) else str(exc)
            if self.telemetry is not None:
                self.telemetry.emit_call(
                    domain="enemy_ai",
                    request=request,
                    success=False,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    error_type=exc.__class__.__name__,
                    error_message=error_msg,
                )
                self.telemetry.emit_validation(
                    domain="enemy_ai",
                    prompt_version=ENEMY_AI_PROMPT_VERSION,
                    valid=False,
                    error_type=exc.__class__.__name__,
                )
            fallback_reason = f"llm_error:{exc.__class__.__name__}"
            self._append_timeline(
                {
                    "kind": "enemy_fallback",
                    "step_count": step_count,
                    "fallback_reason": fallback_reason,
                }
            )
            return self._fallback_action(enemy_id, reason=fallback_reason, legal_action_space=legal_action_space)
        except Exception as exc:  # pragma: no cover
            if self.telemetry is not None:
                self.telemetry.emit_call(
                    domain="enemy_ai",
                    request=request,
                    success=False,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
                self.telemetry.emit_validation(
                    domain="enemy_ai",
                    prompt_version=ENEMY_AI_PROMPT_VERSION,
                    valid=False,
                    error_type=exc.__class__.__name__,
                )
            fallback_reason = f"unexpected_error:{exc.__class__.__name__}"
            self._append_timeline(
                {
                    "kind": "enemy_fallback",
                    "step_count": step_count,
                    "fallback_reason": fallback_reason,
                }
            )
            return self._fallback_action(enemy_id, reason=fallback_reason, legal_action_space=legal_action_space)

        if action.actor_instance_id != enemy_id:
            if self.telemetry is not None:
                self.telemetry.emit_validation("enemy_ai", ENEMY_AI_PROMPT_VERSION, valid=False, error_type="invalid_actor")
            self._append_timeline({"kind": "enemy_fallback", "step_count": step_count, "fallback_reason": "invalid_actor"})
            return self._fallback_action(enemy_id, reason="invalid_actor", legal_action_space=legal_action_space)
        if not self._is_allowed_enemy_action(action):
            if self.telemetry is not None:
                self.telemetry.emit_validation("enemy_ai", ENEMY_AI_PROMPT_VERSION, valid=False, error_type="disallowed_action_type")
            self._append_timeline({"kind": "enemy_fallback", "step_count": step_count, "fallback_reason": "disallowed_action_type"})
            return self._fallback_action(enemy_id, reason="disallowed_action_type", legal_action_space=legal_action_space)
        if not self._validate_combat_targets(action):
            if self.telemetry is not None:
                self.telemetry.emit_validation("enemy_ai", ENEMY_AI_PROMPT_VERSION, valid=False, error_type="invalid_target_payload")
            self._append_timeline({"kind": "enemy_fallback", "step_count": step_count, "fallback_reason": "invalid_target_payload"})
            return self._fallback_action(enemy_id, reason="invalid_target_payload", legal_action_space=legal_action_space)

        is_legal_selection, legal_error = self._is_legal_enemy_selection(action, legal_action_space)
        if not is_legal_selection:
            if self.telemetry is not None:
                self.telemetry.emit_validation("enemy_ai", ENEMY_AI_PROMPT_VERSION, valid=False, error_type=legal_error)
            self._append_timeline(
                {
                    "kind": "enemy_fallback",
                    "step_count": step_count,
                    "fallback_reason": legal_error,
                    "type": action.type.value,
                    "parameters": dict(action.parameters),
                }
            )
            return self._fallback_action(enemy_id, reason=legal_error, legal_action_space=legal_action_space)

        self._append_timeline(
            {
                "kind": "enemy_action_output",
                "step_count": step_count,
                "type": action.type.value,
                "parameters": dict(action.parameters),
            }
        )

        if self.telemetry is not None:
            self.telemetry.emit_call(
                domain="enemy_ai",
                request=request,
                success=True,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                response_text=response_text,
            )
            self.telemetry.emit_validation("enemy_ai", ENEMY_AI_PROMPT_VERSION, valid=True)

        emit_context(
            domain="enemy_ai",
            prompt_version=ENEMY_AI_PROMPT_VERSION,
            step_count=step_count,
            llm_returned_action={
                "type": action.type.value,
                "actor_instance_id": action.actor_instance_id,
                "parameters": dict(action.parameters),
                "metadata": dict(action.metadata),
            },
        )

        return action
