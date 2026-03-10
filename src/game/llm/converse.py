import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from game.llm.client import RetryPolicy, invoke_with_retry
from game.llm.config import LlmSettings
from game.llm.contracts import LlmMessage, LlmRequest
from game.llm.errors import LlmError, LlmSchemaValidationError
from game.llm.json_parse import parse_json_object
from game.llm.prompts import converse as converse_prompt


@dataclass
class ConverseResponder:
    client: Any
    settings: LlmSettings
    retry_policy: RetryPolicy = field(default_factory=lambda: RetryPolicy(max_attempts=2, backoff_seconds=0.0))

    def _build_request(self, player_message: str, state_summary: Dict[str, Any]) -> LlmRequest:
        payload = converse_prompt.build_user_payload(player_message=player_message, state_summary=state_summary)

        return LlmRequest(
            model=self.settings.model,
            messages=[
                LlmMessage(role="system", content=converse_prompt.system_instructions()),
                LlmMessage(role="system", content=json.dumps({"few_shot_examples": converse_prompt.few_shot_examples()})),
                LlmMessage(role="user", content=json.dumps(payload)),
            ],
            temperature=self.settings.conversation.temperature,
            max_tokens=self.settings.conversation.max_tokens,
            timeout_seconds=self.settings.timeout_seconds,
            response_format={"type": "json_schema", "json_schema": converse_prompt.build_response_schema()},
            metadata={"provider": "converse_llm"},
        )

    @staticmethod
    def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        reply = payload.get("reply", "")
        if not isinstance(reply, str) or not reply.strip():
            raise LlmSchemaValidationError("'reply' must be a non-empty string.")

        tone = payload.get("tone", "")
        if tone is None:
            tone = ""
        if not isinstance(tone, str):
            raise LlmSchemaValidationError("'tone' must be a string when provided.")

        metadata = payload.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise LlmSchemaValidationError("'metadata' must be an object when provided.")

        return {
            "reply": reply.strip(),
            "tone": tone.strip(),
            "metadata": dict(metadata),
        }

    def generate(self, player_message: str, state_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        request = self._build_request(player_message=player_message, state_summary=state_summary)

        try:
            response = invoke_with_retry(client=self.client, request=request, retry_policy=self.retry_policy)
            payload = parse_json_object(response.text)
            validated = self._validate_payload(payload)
            return validated
        except LlmError:
            return None
        except Exception:
            return None
