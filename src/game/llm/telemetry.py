import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Protocol

from game.llm.context_window import estimate_tokens_from_text
from game.llm.contracts import LlmRequest


_REDACT_KEYS = {"api_key", "authorization", "token", "secret", "password"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered.endswith("_token_estimate"):
        return False
    return any(part in lowered for part in _REDACT_KEYS)


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, child in value.items():
            if _is_sensitive_key(str(key)):
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = sanitize_payload(child)
        return sanitized
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def _extract_context_token_estimate(request: LlmRequest) -> int:
    for message in request.messages:
        content = (message.content or "").strip()
        if not content.startswith("{"):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        context_envelope = payload.get("context_envelope")
        if context_envelope is None:
            continue
        return estimate_tokens_from_text(json.dumps(context_envelope, ensure_ascii=True, sort_keys=True))
    return 0


class LlmTelemetrySink(Protocol):
    def emit(self, event: Dict[str, Any]) -> None:
        """Persist one telemetry event."""


@dataclass
class InMemoryLlmTelemetrySink(LlmTelemetrySink):
    events: List[Dict[str, Any]] = field(default_factory=list)

    def emit(self, event: Dict[str, Any]) -> None:
        self.events.append(dict(event))


@dataclass
class JsonlLlmTelemetrySink(LlmTelemetrySink):
    base_dir: str = "logs/events"
    file_name: str = "llm_telemetry.jsonl"

    def _resolve_file_path(self) -> Path:
        directory = Path(self.base_dir)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / self.file_name

    def emit(self, event: Dict[str, Any]) -> None:
        file_path = self._resolve_file_path()
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sanitize_payload(event), ensure_ascii=True) + "\n")


@dataclass
class LlmMetricsTracker(LlmTelemetrySink):
    counters: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def emit(self, event: Dict[str, Any]) -> None:
        domain = str(event.get("domain", "unknown"))
        bucket = self.counters.setdefault(
            domain,
            {
                "calls": 0,
                "call_success": 0,
                "call_failure": 0,
                "validation_success": 0,
                "validation_failure": 0,
                "fallbacks": 0,
            },
        )

        kind = str(event.get("kind", ""))
        if kind == "llm_call":
            bucket["calls"] += 1
            if bool(event.get("success", False)):
                bucket["call_success"] += 1
            else:
                bucket["call_failure"] += 1
        elif kind == "llm_validation":
            if bool(event.get("valid", False)):
                bucket["validation_success"] += 1
            else:
                bucket["validation_failure"] += 1
        elif kind == "llm_fallback":
            bucket["fallbacks"] += 1


@dataclass
class LlmTelemetry:
    sinks: List[LlmTelemetrySink] = field(default_factory=list)

    def _emit(self, event: Dict[str, Any]) -> None:
        safe_event = sanitize_payload(event)
        for sink in self.sinks:
            try:
                sink.emit(safe_event)
            except Exception:
                # Telemetry must never block gameplay.
                continue

    @staticmethod
    def _input_token_estimate(request: LlmRequest) -> int:
        joined = "\n".join(message.content for message in request.messages)
        return estimate_tokens_from_text(joined)

    def emit_call(
        self,
        domain: str,
        request: LlmRequest,
        success: bool,
        latency_ms: float,
        response_text: str = "",
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        metadata = dict(request.metadata or {})
        prompt_version = str(metadata.get("prompt_version", "unknown"))

        event: Dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "kind": "llm_call",
            "domain": domain,
            "provider": str(metadata.get("provider", "")),
            "prompt_version": prompt_version,
            "model": request.model,
            "success": bool(success),
            "latency_ms": float(latency_ms),
            "error_type": error_type,
            "token_estimate_input": self._input_token_estimate(request),
            "token_estimate_output": estimate_tokens_from_text(response_text),
            "context_token_estimate": _extract_context_token_estimate(request),
            "beat_count": int(metadata.get("beat_count", 0) or 0),
            "request_metadata": metadata,
        }
        if error_message:
            event["error_message"] = str(error_message)
        self._emit(event)

    def emit_validation(
        self,
        domain: str,
        prompt_version: str,
        valid: bool,
        error_type: str = "",
    ) -> None:
        self._emit(
            {
                "timestamp": _utc_now_iso(),
                "kind": "llm_validation",
                "domain": domain,
                "prompt_version": prompt_version,
                "valid": bool(valid),
                "error_type": error_type,
            }
        )

    def emit_fallback(self, domain: str, prompt_version: str, reason: str) -> None:
        self._emit(
            {
                "timestamp": _utc_now_iso(),
                "kind": "llm_fallback",
                "domain": domain,
                "prompt_version": prompt_version,
                "reason": str(reason),
            }
        )
