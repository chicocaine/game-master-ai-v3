from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from game.llm.bootstrap import LlmClients
from game.llm.config import LlmSettings
from game.llm.contracts import LlmRequest, LlmResponse
from game.llm.errors import LlmConfigurationError, LlmHttpClientError, LlmTimeoutError, LlmTransportError


def _extract_text_from_openai_response(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise LlmTransportError("OpenAI response did not contain choices.")

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content", "") if isinstance(message, dict) else ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        return "\n".join(part for part in text_parts if part).strip()

    return ""


def _normalize_response_format(response_format: dict[str, Any] | None) -> dict[str, Any] | None:
    if not response_format:
        return None

    if response_format.get("type") != "json_schema":
        return response_format

    schema = response_format.get("json_schema")
    if not isinstance(schema, dict):
        return {"type": "json_object"}

    if "schema" in schema and "name" in schema:
        return response_format

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "gm_response",
            # Keep OpenAI schema handling aligned with Python-side jsonschema semantics
            # where object properties are optional unless explicitly listed in `required`.
            "strict": False,
            "schema": schema,
        },
    }


@dataclass
class OpenAiChatCompletionsClient:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"

    def complete(self, request_payload: LlmRequest) -> LlmResponse:
        if not self.api_key:
            raise LlmConfigurationError("LLM_API_KEY is required for OpenAI provider.")

        body = {
            "model": request_payload.model or self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in request_payload.messages],
            "temperature": request_payload.temperature,
            "max_tokens": request_payload.max_tokens,
        }

        normalized_response_format = _normalize_response_format(request_payload.response_format)
        if normalized_response_format is not None:
            body["response_format"] = normalized_response_format

        data = json.dumps(body).encode("utf-8")
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        req = request.Request(
            endpoint,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        timeout_seconds = max(1, int(request_payload.timeout_seconds))
        try:
            with request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            msg = f"OpenAI HTTP error {exc.code}: {body}"
            if exc.code == 401 or exc.code == 403:
                raise LlmConfigurationError(msg) from exc
            if 400 <= exc.code < 500:
                raise LlmHttpClientError(msg, status_code=exc.code) from exc
            raise LlmTransportError(msg) from exc
        except TimeoutError as exc:
            raise LlmTimeoutError(str(exc) or "OpenAI request timed out") from exc
        except error.URLError as exc:
            raise LlmTransportError(str(exc.reason) if hasattr(exc, "reason") else str(exc)) from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LlmTransportError("OpenAI response was not valid JSON.") from exc

        text = _extract_text_from_openai_response(parsed)
        usage = parsed.get("usage", {}) if isinstance(parsed.get("usage", {}), dict) else {}
        finish_reason = ""
        choices = parsed.get("choices", [])
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish_reason = str(choices[0].get("finish_reason", ""))

        return LlmResponse(text=text, finish_reason=finish_reason, usage=usage, raw=parsed)


@dataclass
class MockEchoClient:
    domain: str

    def complete(self, request_payload: LlmRequest) -> LlmResponse:
        _ = request_payload
        if self.domain == "player_intent":
            return LlmResponse(text='{"type":"converse","parameters":{"message":"I need more detail to act."}}')
        if self.domain == "enemy_ai":
            return LlmResponse(text='{"type":"end_turn","parameters":{}}')
        if self.domain == "narration":
            return LlmResponse(text='{"text":"The scene shifts as your choice resolves."}')
        if self.domain == "converse":
            return LlmResponse(text='{"reply":"I hear you. Give me one more concrete detail and I will resolve it.","tone":"helpful"}')
        return LlmResponse(text='{"reply":"..."}')


def create_live_llm_clients(settings: LlmSettings) -> LlmClients:
    provider = settings.provider.strip().lower()
    if provider == "mock":
        return LlmClients(
            player_intent=MockEchoClient(domain="player_intent"),
            enemy_ai=MockEchoClient(domain="enemy_ai"),
            narration=MockEchoClient(domain="narration"),
            converse=MockEchoClient(domain="converse"),
        )

    if provider == "openai":
        base_url = os.environ.get("LLM_OPENAI_BASE_URL", "https://api.openai.com/v1")
        shared = OpenAiChatCompletionsClient(
            api_key=settings.api_key,
            model=settings.model,
            base_url=base_url,
        )
        return LlmClients(
            player_intent=shared,
            enemy_ai=shared,
            narration=shared,
            converse=shared,
        )

    raise LlmConfigurationError(f"Unsupported live LLM provider '{settings.provider}'.")
