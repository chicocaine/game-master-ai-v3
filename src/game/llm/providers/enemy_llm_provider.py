import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.action import Action, create_action
from core.enums import ActionType

from game.engine.interfaces import ActionProvider, EngineContext
from game.enums import GameState
from game.llm.client import RetryPolicy, invoke_with_retry
from game.llm.config import LlmSettings
from game.llm.context_window import fit_dict_to_token_budget
from game.llm.contracts import LlmMessage, LlmRequest
from game.llm.errors import LlmError
from game.llm.fewshot import get_few_shot_examples_with_budget
from game.llm.json_parse import parse_json_object, validate_action_payload
from game.llm.prompts import enemy_ai


@dataclass
class EnemyLlmActionProvider(ActionProvider):
    client: Any
    settings: LlmSettings
    retry_policy: RetryPolicy = field(default_factory=lambda: RetryPolicy(max_attempts=2, backoff_seconds=0.0))
    include_provider_metadata: bool = True

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
            "player_targets": player_targets,
            "enemies": enemy_status,
        }

    def _fallback_action(self, enemy_id: str, reason: str) -> Action:
        metadata = {
            "provider": "enemy_llm",
            "fallback": True,
            "fallback_reason": reason,
        }
        return create_action(
            action_type=ActionType.END_TURN,
            parameters={},
            actor_instance_id=enemy_id,
            metadata=metadata,
        )

    def _build_request(self, enemy_id: str, enemy_persona: str, combat_summary: Dict[str, Any]) -> LlmRequest:
        compact_summary = fit_dict_to_token_budget(
            combat_summary,
            max_tokens=max(96, self.settings.enemy.max_tokens // 2),
            priority_keys=["state", "current_enemy_id", "turn_order", "player_targets"],
        )
        payload = enemy_ai.build_user_payload(
            actor_instance_id=enemy_id,
            enemy_persona=enemy_persona,
            combat_summary=compact_summary,
        )
        schema = enemy_ai.build_response_schema()
        examples = get_few_shot_examples_with_budget(
            domain="enemy_ai",
            max_examples=4,
            max_tokens=max(64, self.settings.enemy.max_tokens // 4),
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

    def next_action(self, session: Any, ctx: EngineContext) -> Optional[Action]:
        enemy_id = self._current_turn_enemy_id(session)
        if not enemy_id:
            return None

        enemy = self._enemy_for_id(session, enemy_id)
        enemy_persona = str(getattr(enemy, "persona", "") or "")
        combat_summary = self._summarize_combat(session, current_enemy_id=enemy_id)
        request = self._build_request(enemy_id=enemy_id, enemy_persona=enemy_persona, combat_summary=combat_summary)

        try:
            response = invoke_with_retry(client=self.client, request=request, retry_policy=self.retry_policy)
            payload = parse_json_object(response.text)
            action = self._action_from_payload(payload, enemy_id=enemy_id)
        except LlmError as exc:
            return self._fallback_action(enemy_id, reason=f"llm_error:{exc.__class__.__name__}")
        except Exception as exc:  # pragma: no cover
            return self._fallback_action(enemy_id, reason=f"unexpected_error:{exc.__class__.__name__}")

        if action.actor_instance_id != enemy_id:
            return self._fallback_action(enemy_id, reason="invalid_actor")
        if not self._is_allowed_enemy_action(action):
            return self._fallback_action(enemy_id, reason="disallowed_action_type")
        if not self._validate_combat_targets(action):
            return self._fallback_action(enemy_id, reason="invalid_target_payload")

        return action
