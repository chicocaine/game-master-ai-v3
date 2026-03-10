import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.enums import EventType
from game.llm.client import RetryPolicy, invoke_with_retry
from game.llm.config import LlmSettings
from game.llm.contracts import LlmMessage, LlmRequest
from game.llm.converse import ConverseResponder
from game.llm.errors import LlmError
from game.llm.json_parse import parse_json_object, validate_narration_payload
from game.llm.prompts import narration as narration_prompt
from game.llm.routing import build_state_summary


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
    trigger_types: set[str] = field(default_factory=lambda: set(DEFAULT_NARRATION_TRIGGER_TYPES))

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
        payload = narration_prompt.build_user_payload(events=events, state_summary=build_state_summary(session))

        return LlmRequest(
            model=self.settings.model,
            messages=[
                LlmMessage(role="system", content=narration_prompt.system_instructions()),
                LlmMessage(role="system", content=json.dumps({"few_shot_examples": narration_prompt.few_shot_examples()})),
                LlmMessage(role="user", content=json.dumps(payload)),
            ],
            temperature=self.settings.narration.temperature,
            max_tokens=self.settings.narration.max_tokens,
            timeout_seconds=self.settings.timeout_seconds,
            response_format={"type": "json_schema", "json_schema": narration_prompt.build_response_schema()},
            metadata={"provider": "narration_llm"},
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
        if not self.should_narrate(events):
            return None

        if EventType.CONVERSE.value in self._event_types(events):
            converse_reply = self._generate_converse(events, session)
            if converse_reply:
                return converse_reply

        request = self._narration_request(events=events, session=session)
        try:
            response = invoke_with_retry(client=self.client, request=request, retry_policy=self.retry_policy)
            payload = parse_json_object(response.text)
            validated = validate_narration_payload(payload)
            return validated["text"]
        except LlmError:
            return None
        except Exception:
            return None
