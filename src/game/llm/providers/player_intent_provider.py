from collections import deque
from dataclasses import dataclass, field
import json
import time
from typing import Any, Deque, Dict, Optional

from game.core.action import Action
from game.core.action import create_action
from game.core.action import validate_action
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
from game.llm.prompts.base import allowed_action_values_for_state
from game.llm.routing import build_state_summary, prompt_module_for_state
from game.llm.telemetry import LlmTelemetry


PLAYER_INTENT_PROMPT_VERSION = "player_intent.v2"


@dataclass(frozen=True)
class PlayerInputMessage:
    text: str
    actor_instance_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlayerIntentLlmProvider(ActionProvider):
    client: Any
    settings: LlmSettings
    retry_policy: RetryPolicy = field(default_factory=lambda: RetryPolicy(max_attempts=2, backoff_seconds=0.0))
    telemetry: LlmTelemetry | None = None
    include_provider_metadata: bool = True
    queue: Deque[PlayerInputMessage] = field(default_factory=deque)
    timeline: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=40))

    def _append_timeline(self, entry: Dict[str, Any]) -> None:
        self.timeline.append(dict(entry))

    def enqueue(self, text: str, actor_instance_id: str = "", metadata: Dict[str, Any] | None = None) -> None:
        self._append_timeline(
            {
                "kind": "player_input",
                "actor_instance_id": str(actor_instance_id),
                "player_input": str(text),
            }
        )
        self.queue.append(
            PlayerInputMessage(
                text=str(text),
                actor_instance_id=str(actor_instance_id),
                metadata=dict(metadata or {}),
            )
        )

    def pending_count(self) -> int:
        return len(self.queue)

    @staticmethod
    def _is_underspecified_input(text: str) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return True
        ambiguous_exact = {
            "?",
            "idk",
            "uh",
            "huh",
            "maybe",
        }
        if normalized in ambiguous_exact:
            return True
        if len(normalized.split()) <= 2 and normalized.endswith("?"):
            return True
        return False

    def _build_request(self, session: Any, user_message: PlayerInputMessage, step_count: int | None = None) -> LlmRequest:
        prompt_module = prompt_module_for_state(session.state)
        state_summary = build_state_summary(session)
        allowed_actions = self._allowed_action_values(session)
        context_envelope = build_context_envelope(
            current_context=state_summary,
            allowed_actions=allowed_actions,
            actor_context={
                "actor_instance_id": user_message.actor_instance_id,
                "source": "player",
            },
            timeline_entries=list(self.timeline),
            max_timeline_items=12,
            max_timeline_tokens=max(96, self.settings.action.max_tokens // 3),
        )

        payload = prompt_module.build_user_payload(
            player_input=user_message.text,
            actor_instance_id=user_message.actor_instance_id,
            state_summary=state_summary,
            context_envelope=context_envelope,
        )
        payload["recent_conversation"] = self._recent_conversation_for_prompt(max_items=8)
        payload = fit_dict_to_token_budget(
            payload,
            max_tokens=max(128, self.settings.action.max_tokens // 2),
            priority_keys=["state", "allowed_actions", "player_input", "recent_conversation", "state_summary", "context_envelope"],
        )
        response_schema = prompt_module.build_response_schema()
        examples = get_few_shot_examples_with_budget(
            domain=session.state.value,
            max_examples=4,
            max_tokens=max(64, self.settings.action.max_tokens // 4),
        )

        emit_context(
            domain="player_intent",
            prompt_version=PLAYER_INTENT_PROMPT_VERSION,
            step_count=step_count,
            state_summary=state_summary,
            context_envelope=context_envelope,
            few_shot_examples=examples,
        )

        messages = [
            LlmMessage(role="system", content=prompt_module.system_instructions()),
            LlmMessage(role="system", content=json.dumps({"few_shot_examples": examples})),
            LlmMessage(role="user", content=json.dumps(payload)),
        ]

        return LlmRequest(
            model=self.settings.model,
            messages=messages,
            temperature=self.settings.action.temperature,
            max_tokens=self.settings.action.max_tokens,
            timeout_seconds=self.settings.timeout_seconds,
            response_format={"type": "json_schema", "json_schema": response_schema},
            metadata={
                "provider": "player_intent_llm",
                "state": session.state.value,
                "prompt_version": PLAYER_INTENT_PROMPT_VERSION,
            },
        )

    def _recent_conversation_for_prompt(self, max_items: int = 8) -> list[dict[str, Any]]:
        items = list(self.timeline)[-max_items:]
        compact: list[dict[str, Any]] = []
        for item in items:
            entry: dict[str, Any] = {}
            kind = item.get("kind")
            if isinstance(kind, str) and kind:
                entry["kind"] = kind

            player_input = item.get("player_input")
            if isinstance(player_input, str) and player_input.strip():
                entry["player_input"] = player_input

            action_type = item.get("type")
            if isinstance(action_type, str) and action_type:
                entry["action_type"] = action_type

            parameters = item.get("parameters")
            if isinstance(parameters, dict) and parameters:
                entry["parameters"] = dict(parameters)

            fallback_reason = item.get("fallback_reason")
            if isinstance(fallback_reason, str) and fallback_reason:
                entry["fallback_reason"] = fallback_reason

            converse_message = item.get("converse_message")
            if isinstance(converse_message, str) and converse_message.strip():
                entry["converse_message"] = converse_message

            if entry:
                compact.append(entry)
        return compact

    def _allowed_action_values(self, session: Any) -> list[str]:
        return allowed_action_values_for_state(session.state)

    @staticmethod
    def _player_text_for_converse(user_message: PlayerInputMessage) -> str:
        text = str(user_message.text or "").strip()
        return text if text else "I need clarification."

    def _route_to_converse(
        self,
        *,
        user_message: PlayerInputMessage,
        reason: str,
        reasoning: str,
        metadata_extra: Dict[str, Any] | None = None,
    ) -> Action:
        player_text = self._player_text_for_converse(user_message)
        metadata: Dict[str, Any] = {
            "provider": "player_intent_llm",
            "fallback": True,
            "fallback_reason": reason,
        }
        if metadata_extra:
            metadata.update(dict(metadata_extra))
        if self.include_provider_metadata and user_message.metadata:
            metadata["input_metadata"] = dict(user_message.metadata)

        return create_action(
            action_type=ActionType.CONVERSE,
            parameters={"message": player_text},
            actor_instance_id=user_message.actor_instance_id,
            raw_input=user_message.text,
            reasoning=reasoning,
            metadata=metadata,
        )

    def _fallback_action(self, user_message: PlayerInputMessage, reason: str) -> Optional[Action]:
        stripped = user_message.text.strip()
        if not stripped:
            return None
        self._append_timeline(
            {
                "kind": "parser_fallback",
                "actor_instance_id": user_message.actor_instance_id,
                "fallback_reason": reason,
                "converse_message": stripped,
            }
        )
        if self.telemetry is not None:
            self.telemetry.emit_fallback("player_intent", PLAYER_INTENT_PROMPT_VERSION, reason)
        return self._route_to_converse(
            user_message=user_message,
            reason=reason,
            reasoning="The parser could not safely produce a valid non-converse action, so conversation is required.",
        )

    def _clarification_converse(self, user_message: PlayerInputMessage) -> Action:
        self._append_timeline(
            {
                "kind": "clarification_requested",
                "actor_instance_id": user_message.actor_instance_id,
                "player_input": user_message.text,
            }
        )
        if self.telemetry is not None:
            self.telemetry.emit_fallback("player_intent", PLAYER_INTENT_PROMPT_VERSION, "ambiguous_input")

        return self._route_to_converse(
            user_message=user_message,
            reason="ambiguous_input",
            reasoning=(
                "The player's message is too ambiguous to determine complete required parameters, "
                "so this is routed to converse for clarification."
            ),
        )

    def _action_from_payload(self, payload: dict[str, Any], user_message: PlayerInputMessage) -> Action:
        validated = validate_action_payload(payload)
        action_type = str(validated["type"])
        normalized_parameters = dict(validated["parameters"])
        if action_type in {"converse", "query", "interact"}:
            normalized_parameters["message"] = self._player_text_for_converse(user_message)

        reasoning = str(validated["reasoning"] or "").strip()
        if not reasoning:
            if action_type in {"converse", "query", "interact"}:
                reasoning = (
                    "The input does not provide complete parameters for a concrete gameplay action; "
                    "route to converse for clarification."
                )
            else:
                reasoning = "Action selected from player intent and current state constraints."

        action_data = {
            "type": action_type,
            "parameters": normalized_parameters,
            "actor_instance_id": validated["actor_instance_id"] or user_message.actor_instance_id,
            "raw_input": user_message.text,
            "reasoning": reasoning,
            "metadata": validated["metadata"],
        }

        if self.include_provider_metadata:
            metadata = dict(action_data.get("metadata", {}))
            metadata["provider"] = "player_intent_llm"
            if user_message.metadata:
                metadata["input_metadata"] = dict(user_message.metadata)
            action_data["metadata"] = metadata

        return Action.from_dict(action_data)

    def _blocked_start_converse(self, session: Any, user_message: PlayerInputMessage) -> Optional[Action]:
        if getattr(session, "state", None) is not GameState.PREGAME:
            return None

        missing: list[str] = []
        if not list(getattr(session, "party", [])):
            missing.append("at least one player")
        if getattr(session, "dungeon", None) is None:
            missing.append("a dungeon selection")

        if not missing:
            return None

        if len(missing) == 1:
            requirement_text = missing[0]
        elif len(missing) == 2:
            requirement_text = f"{missing[0]} and {missing[1]}"
        else:
            requirement_text = ", and ".join([", ".join(missing[:-1]), missing[-1]])

        self._append_timeline(
            {
                "kind": "blocked_start",
                "actor_instance_id": user_message.actor_instance_id,
                "missing_requirements": list(missing),
            }
        )

        return self._route_to_converse(
            user_message=user_message,
            reason="blocked_start",
            reasoning=f"Cannot execute start because setup is incomplete: {requirement_text}.",
            metadata_extra={"missing_requirements": list(missing)},
        )

    def next_action(self, session: Any, ctx: EngineContext) -> Optional[Action]:
        if not self.queue:
            return None

        user_message = self.queue.popleft()
        step_count = int(getattr(ctx, "step_count", 0))
        if self._is_underspecified_input(user_message.text):
            action = self._clarification_converse(user_message)
            self._append_timeline({"kind": "llm_action_parser_output", "step_count": step_count, "type": action.type.value, "parameters": dict(action.parameters)})
            return action

        request = self._build_request(session, user_message, step_count=step_count)
        started = time.perf_counter()
        response_text = ""

        try:
            response = invoke_with_retry(
                client=self.client,
                request=request,
                retry_policy=self.retry_policy,
            )
            response_text = response.text
            payload = parse_json_object(response.text)
            action = self._action_from_payload(payload, user_message)
        except LlmError as exc:
            error_msg = str(exc.last_error) if isinstance(exc, LlmRetryExhaustedError) else str(exc)
            if self.telemetry is not None:
                self.telemetry.emit_call(
                    domain="player_intent",
                    request=request,
                    success=False,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    error_type=exc.__class__.__name__,
                    error_message=error_msg,
                )
                self.telemetry.emit_validation(
                    domain="player_intent",
                    prompt_version=PLAYER_INTENT_PROMPT_VERSION,
                    valid=False,
                    error_type=exc.__class__.__name__,
                )
            return self._fallback_action(user_message, reason=f"llm_error:{exc.__class__.__name__}")
        except Exception as exc:  # pragma: no cover - defensive safety
            if self.telemetry is not None:
                self.telemetry.emit_call(
                    domain="player_intent",
                    request=request,
                    success=False,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
                self.telemetry.emit_validation(
                    domain="player_intent",
                    prompt_version=PLAYER_INTENT_PROMPT_VERSION,
                    valid=False,
                    error_type=exc.__class__.__name__,
                )
            return self._fallback_action(user_message, reason=f"unexpected_error:{exc.__class__.__name__}")

        allowed_actions = set(self._allowed_action_values(session))
        if action.type.value not in allowed_actions:
            if self.telemetry is not None:
                self.telemetry.emit_validation(
                    domain="player_intent",
                    prompt_version=PLAYER_INTENT_PROMPT_VERSION,
                    valid=False,
                    error_type="disallowed_action_type",
                )
            return self._route_to_converse(
                user_message=user_message,
                reason="disallowed_action_type",
                reasoning=(
                    f"Model returned disallowed action type '{action.type.value}' for state '{session.state.value}'."
                ),
            )

        if action.type is ActionType.START:
            blocked = self._blocked_start_converse(session, user_message)
            if blocked is not None:
                if self.telemetry is not None:
                    self.telemetry.emit_fallback("player_intent", PLAYER_INTENT_PROMPT_VERSION, "blocked_start")
                return blocked

        action_errors = validate_action(action)
        if action_errors:
            if self.telemetry is not None:
                self.telemetry.emit_validation(
                    domain="player_intent",
                    prompt_version=PLAYER_INTENT_PROMPT_VERSION,
                    valid=False,
                    error_type="invalid_action_parameters",
                )
            return self._route_to_converse(
                user_message=user_message,
                reason="invalid_action_parameters",
                reasoning=(
                    "Model output did not satisfy required action parameters: "
                    + "; ".join(action_errors)
                ),
                metadata_extra={"validation_errors": list(action_errors)},
            )

        self._append_timeline(
            {
                "kind": "llm_action_parser_output",
                "step_count": step_count,
                "actor_instance_id": action.actor_instance_id,
                "type": action.type.value,
                "parameters": dict(action.parameters),
            }
        )

        if self.telemetry is not None:
            self.telemetry.emit_call(
                domain="player_intent",
                request=request,
                success=True,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                response_text=response_text,
            )
            self.telemetry.emit_validation(
                domain="player_intent",
                prompt_version=PLAYER_INTENT_PROMPT_VERSION,
                valid=True,
            )

        emit_context(
            domain="player_intent",
            prompt_version=PLAYER_INTENT_PROMPT_VERSION,
            step_count=step_count,
            llm_returned_action={
                "type": action.type.value,
                "actor_instance_id": action.actor_instance_id,
                "parameters": dict(action.parameters),
                "metadata": dict(action.metadata),
            },
        )

        return action
