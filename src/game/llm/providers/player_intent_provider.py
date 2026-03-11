from collections import deque
from dataclasses import dataclass, field
import json
import time
from typing import Any, Deque, Dict, Optional

from game.core.action import Action
from game.core.action import create_action
from game.core.enums import ActionType
from game.engine.interfaces import ActionProvider, EngineContext
from game.enums import GameState
from game.llm.client import RetryPolicy, invoke_with_retry
from game.llm.config import LlmSettings
from game.llm.converse import ConverseResponder
from game.llm.context_builder import build_context_envelope
from game.llm.context_window import fit_dict_to_token_budget
from game.llm.contracts import LlmMessage, LlmRequest
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
    converse_responder: ConverseResponder | None = None
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

    def _build_request(self, session: Any, user_message: PlayerInputMessage) -> LlmRequest:
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
        payload = fit_dict_to_token_budget(
            payload,
            max_tokens=max(128, self.settings.action.max_tokens // 2),
            priority_keys=["state", "allowed_actions", "player_input", "state_summary", "context_envelope"],
        )
        response_schema = prompt_module.build_response_schema()
        examples = get_few_shot_examples_with_budget(
            domain=session.state.value,
            max_examples=4,
            max_tokens=max(64, self.settings.action.max_tokens // 4),
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

    def _allowed_action_values(self, session: Any) -> list[str]:
        return allowed_action_values_for_state(session.state)

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
        metadata: Dict[str, Any] = {
            "provider": "player_intent_llm",
            "fallback": True,
            "fallback_reason": reason,
        }
        if self.include_provider_metadata and user_message.metadata:
            metadata["input_metadata"] = dict(user_message.metadata)

        return create_action(
            action_type=ActionType.CONVERSE,
            parameters={"message": stripped},
            actor_instance_id=user_message.actor_instance_id,
            raw_input=user_message.text,
            metadata=metadata,
        )

    def _clarification_converse(self, user_message: PlayerInputMessage) -> Action:
        message = (
            "I need a bit more detail to resolve that action. "
            "Tell me your exact intent, target, or destination."
        )
        self._append_timeline(
            {
                "kind": "clarification_requested",
                "actor_instance_id": user_message.actor_instance_id,
                "player_input": user_message.text,
            }
        )
        if self.telemetry is not None:
            self.telemetry.emit_fallback("player_intent", PLAYER_INTENT_PROMPT_VERSION, "ambiguous_input")

        return create_action(
            action_type=ActionType.CONVERSE,
            parameters={"message": message},
            actor_instance_id=user_message.actor_instance_id,
            raw_input=user_message.text,
            metadata={
                "provider": "player_intent_llm",
                "fallback": True,
                "fallback_reason": "ambiguous_input",
            },
        )

    def _action_from_payload(self, payload: dict[str, Any], user_message: PlayerInputMessage) -> Action:
        validated = validate_action_payload(payload)
        action_data = {
            "type": validated["type"],
            "parameters": validated["parameters"],
            "actor_instance_id": validated["actor_instance_id"] or user_message.actor_instance_id,
            "raw_input": user_message.text,
            "reasoning": validated["reasoning"],
            "metadata": validated["metadata"],
        }

        if self.include_provider_metadata:
            metadata = dict(action_data.get("metadata", {}))
            metadata["provider"] = "player_intent_llm"
            if user_message.metadata:
                metadata["input_metadata"] = dict(user_message.metadata)
            action_data["metadata"] = metadata

        return Action.from_dict(action_data)

    def _route_converse_action(self, action: Action, session: Any, user_message: PlayerInputMessage) -> Action:
        if action.type is not ActionType.CONVERSE:
            return action
        if self.converse_responder is None:
            return action

        response = self.converse_responder.generate(
            player_message=str(action.parameters.get("message", user_message.text)),
            state_summary=build_state_summary(session),
        )
        if response is None:
            return action

        self._append_timeline(
            {
                "kind": "llm_converse_output",
                "actor_instance_id": user_message.actor_instance_id,
                "reply": str(response.get("reply", "")),
                "tone": str(response.get("tone", "")),
            }
        )

        metadata = dict(action.metadata)
        metadata["converse_response"] = {
            "reply": str(response.get("reply", "")),
            "tone": str(response.get("tone", "")),
            "metadata": dict(response.get("metadata", {})),
        }
        action.metadata = metadata
        return action

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

        message = f"You cannot start yet. Please set up {requirement_text} first."
        self._append_timeline(
            {
                "kind": "blocked_start",
                "actor_instance_id": user_message.actor_instance_id,
                "missing_requirements": list(missing),
            }
        )

        return create_action(
            action_type=ActionType.CONVERSE,
            parameters={"message": message},
            actor_instance_id=user_message.actor_instance_id,
            raw_input=user_message.text,
            metadata={
                "provider": "player_intent_llm",
                "fallback": True,
                "fallback_reason": "blocked_start",
                "missing_requirements": list(missing),
            },
        )

    def next_action(self, session: Any, ctx: EngineContext) -> Optional[Action]:
        if not self.queue:
            return None

        user_message = self.queue.popleft()
        if self._is_underspecified_input(user_message.text):
            return self._clarification_converse(user_message)

        request = self._build_request(session, user_message)
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
            return self._fallback_action(user_message, reason="disallowed_action_type")

        if action.type is ActionType.START:
            blocked = self._blocked_start_converse(session, user_message)
            if blocked is not None:
                if self.telemetry is not None:
                    self.telemetry.emit_fallback("player_intent", PLAYER_INTENT_PROMPT_VERSION, "blocked_start")
                return blocked

        self._append_timeline(
            {
                "kind": "llm_action_parser_output",
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

        return self._route_converse_action(action=action, session=session, user_message=user_message)
