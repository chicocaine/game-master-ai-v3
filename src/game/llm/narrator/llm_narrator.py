import json
from dataclasses import dataclass, field
from collections import deque
import time
from typing import Any, Dict, List, Optional

from core.enums import EventType
from game.llm.client import RetryPolicy, invoke_with_retry
from game.llm.config import LlmSettings
from game.llm.context_builder import build_context_envelope
from game.llm.context_window import build_recent_window, fit_dict_to_token_budget
from game.llm.contracts import LlmMessage, LlmRequest
from game.llm.converse import ConverseResponder
from game.llm.errors import LlmError
from game.llm.fewshot import get_few_shot_examples_with_budget
from game.llm.json_parse import parse_json_object, validate_narration_payload
from game.llm.prompts import narration as narration_prompt
from game.llm.routing import build_state_summary
from game.llm.telemetry import LlmTelemetry


NARRATION_PROMPT_VERSION = "narration.v1"


DEFAULT_NARRATION_TRIGGER_TYPES = {
    EventType.ROOM_ENTERED.value,
    EventType.ATTACK_HIT.value,
    EventType.ATTACK_MISSED.value,
    EventType.DAMAGE_APPLIED.value,
    EventType.SPELL_CAST.value,
    EventType.ENCOUNTER_ENDED.value,
    EventType.GAME_STARTED.value,
    EventType.CONVERSE.value,
}


@dataclass
class LlmNarrator:
    client: Any
    settings: LlmSettings
    retry_policy: RetryPolicy = field(default_factory=lambda: RetryPolicy(max_attempts=2, backoff_seconds=0.0))
    converse_responder: ConverseResponder | None = None
    telemetry: LlmTelemetry | None = None
    trigger_types: set[str] = field(default_factory=lambda: set(DEFAULT_NARRATION_TRIGGER_TYPES))
    timeline: deque = field(default_factory=lambda: deque(maxlen=60))

    def _append_timeline(self, entry: Dict[str, Any]) -> None:
        self.timeline.append(dict(entry))

    @staticmethod
    def _event_types(events: List[Dict[str, Any]]) -> set[str]:
        types: set[str] = set()
        for event in events:
            event_type = event.get("type")
            if isinstance(event_type, str) and event_type:
                types.add(event_type)
        return types

    def should_narrate(self, events: List[Dict[str, Any]]) -> bool:
        return bool(self._event_types(events) & self.trigger_types)

    def _first_converse_message(self, events: List[Dict[str, Any]]) -> str:
        for event in events:
            if str(event.get("type", "")) == EventType.CONVERSE.value:
                message = event.get("message", "")
                if isinstance(message, str):
                    return message
        return ""

    def _narration_request(self, events: List[Dict[str, Any]], session: Any) -> LlmRequest:
        recent_events = build_recent_window(
            events,
            max_items=12,
            max_tokens=max(96, self.settings.narration.max_tokens // 2),
        )
        state_summary = build_state_summary(session)
        context_envelope = build_context_envelope(
            current_context=state_summary,
            allowed_actions=["narrate", "converse"],
            actor_context={"source": "narrator"},
            timeline_entries=list(self.timeline),
            max_timeline_items=16,
            max_timeline_tokens=max(96, self.settings.narration.max_tokens // 3),
        )
        payload = narration_prompt.build_user_payload(
            events=recent_events,
            state_summary=state_summary,
            context_envelope=context_envelope,
        )
        payload = fit_dict_to_token_budget(
            payload,
            max_tokens=max(128, self.settings.narration.max_tokens // 2),
            priority_keys=["domain", "events", "state_summary", "context_envelope"],
        )
        examples = get_few_shot_examples_with_budget(
            domain="narration",
            max_examples=3,
            max_tokens=max(64, self.settings.narration.max_tokens // 4),
        )

        return LlmRequest(
            model=self.settings.model,
            messages=[
                LlmMessage(role="system", content=narration_prompt.system_instructions()),
                LlmMessage(role="system", content=json.dumps({"few_shot_examples": examples})),
                LlmMessage(role="user", content=json.dumps(payload)),
            ],
            temperature=self.settings.narration.temperature,
            max_tokens=self.settings.narration.max_tokens,
            timeout_seconds=self.settings.timeout_seconds,
            response_format={"type": "json_schema", "json_schema": narration_prompt.build_response_schema()},
            metadata={"provider": "narration_llm", "prompt_version": NARRATION_PROMPT_VERSION},
        )

    def _generate_converse(self, events: List[Dict[str, Any]], session: Any) -> Optional[str]:
        if self.converse_responder is None:
            return None

        player_message = self._first_converse_message(events)
        if not player_message:
            return None

        payload = self.converse_responder.generate(
            player_message=player_message,
            state_summary=build_state_summary(session),
        )
        if payload is None:
            return None
        return str(payload.get("reply", "")).strip() or None

    def narrate(self, events: List[Dict[str, Any]], session: Any, ctx: Any) -> Optional[str]:
        if not events:
            return None
        self._append_timeline({"kind": "events", "events": list(events)})
        if not self.should_narrate(events):
            return None

        if EventType.CONVERSE.value in self._event_types(events):
            converse_reply = self._generate_converse(events, session)
            if converse_reply:
                return converse_reply

        request = self._narration_request(events=events, session=session)
        started = time.perf_counter()
        response_text = ""
        try:
            response = invoke_with_retry(client=self.client, request=request, retry_policy=self.retry_policy)
            response_text = response.text
            payload = parse_json_object(response.text)
            validated = validate_narration_payload(payload)
            self._append_timeline({"kind": "llm_narrator_output", "text": validated["text"]})
            if self.telemetry is not None:
                self.telemetry.emit_call(
                    domain="narration",
                    request=request,
                    success=True,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    response_text=response_text,
                )
                self.telemetry.emit_validation("narration", NARRATION_PROMPT_VERSION, valid=True)
            return validated["text"]
        except LlmError as exc:
            if self.telemetry is not None:
                self.telemetry.emit_call(
                    domain="narration",
                    request=request,
                    success=False,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    error_type=exc.__class__.__name__,
                )
                self.telemetry.emit_validation("narration", NARRATION_PROMPT_VERSION, valid=False, error_type=exc.__class__.__name__)
            return None
        except Exception as exc:
            if self.telemetry is not None:
                self.telemetry.emit_call(
                    domain="narration",
                    request=request,
                    success=False,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    error_type=exc.__class__.__name__,
                )
                self.telemetry.emit_validation("narration", NARRATION_PROMPT_VERSION, valid=False, error_type=exc.__class__.__name__)
            return None
