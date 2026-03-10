from dataclasses import dataclass
import os
from typing import Mapping

from game.llm.errors import LlmConfigurationError


SUPPORTED_PROVIDERS = {"openai", "mock"}


@dataclass(frozen=True)
class LlmDomainSettings:
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class LlmSettings:
    api_key: str
    provider: str
    model: str
    timeout_seconds: int
    action: LlmDomainSettings
    enemy: LlmDomainSettings
    narration: LlmDomainSettings
    conversation: LlmDomainSettings


def _get_value(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key)
    if value is None:
        return default
    return str(value).strip()


def _parse_float(env: Mapping[str, str], key: str, default: str) -> float:
    raw = _get_value(env, key, default)
    try:
        return float(raw)
    except ValueError as exc:
        raise LlmConfigurationError(f"Invalid float for '{key}': {raw!r}") from exc


def _parse_int(env: Mapping[str, str], key: str, default: str) -> int:
    raw = _get_value(env, key, default)
    try:
        return int(raw)
    except ValueError as exc:
        raise LlmConfigurationError(f"Invalid int for '{key}': {raw!r}") from exc


def _validate_temperature(key: str, value: float) -> None:
    if value < 0.0 or value > 2.0:
        raise LlmConfigurationError(f"'{key}' must be between 0.0 and 2.0. Got {value}.")


def _validate_max_tokens(key: str, value: int) -> None:
    if value <= 0:
        raise LlmConfigurationError(f"'{key}' must be > 0. Got {value}.")


def load_llm_settings(
    env: Mapping[str, str] | None = None,
    require_api_key: bool = True,
) -> LlmSettings:
    source = env or os.environ

    api_key = _get_value(source, "LLM_API_KEY", "")
    provider = _get_value(source, "LLM_PROVIDER", "openai").lower()
    model = _get_value(source, "LLM_MODEL", "gpt-4.1-mini")
    timeout_seconds = _parse_int(source, "LLM_TIMEOUT_SECONDS", "30")

    global_temperature = _parse_float(source, "LLM_TEMPERATURE", "0.3")
    global_max_tokens = _parse_int(source, "LLM_MAX_TOKENS", "2048")

    action_temperature = _parse_float(source, "LLM_TEMPERATURE_ACTION", str(global_temperature))
    enemy_temperature = _parse_float(source, "LLM_TEMPERATURE_ENEMY", str(global_temperature))
    narration_temperature = _parse_float(source, "LLM_TEMPERATURE_NARRATION", str(global_temperature))
    conversation_temperature = _parse_float(source, "LLM_TEMPERATURE_CONVERSATION", str(global_temperature))

    action_max_tokens = _parse_int(source, "LLM_MAX_TOKENS_ACTION", str(global_max_tokens))
    enemy_max_tokens = _parse_int(source, "LLM_MAX_TOKENS_ENEMY", str(global_max_tokens))
    narration_max_tokens = _parse_int(source, "LLM_MAX_TOKENS_NARRATION", str(global_max_tokens))
    conversation_max_tokens = _parse_int(source, "LLM_MAX_TOKENS_CONVERSATION", str(global_max_tokens))

    if require_api_key and not api_key:
        raise LlmConfigurationError("LLM_API_KEY is required when LLM mode is enabled.")
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise LlmConfigurationError(f"Unsupported LLM_PROVIDER '{provider}'. Supported: {supported}.")
    if not model:
        raise LlmConfigurationError("LLM_MODEL cannot be empty.")
    if timeout_seconds <= 0:
        raise LlmConfigurationError(f"LLM_TIMEOUT_SECONDS must be > 0. Got {timeout_seconds}.")

    _validate_temperature("LLM_TEMPERATURE", global_temperature)
    _validate_temperature("LLM_TEMPERATURE_ACTION", action_temperature)
    _validate_temperature("LLM_TEMPERATURE_ENEMY", enemy_temperature)
    _validate_temperature("LLM_TEMPERATURE_NARRATION", narration_temperature)
    _validate_temperature("LLM_TEMPERATURE_CONVERSATION", conversation_temperature)

    _validate_max_tokens("LLM_MAX_TOKENS", global_max_tokens)
    _validate_max_tokens("LLM_MAX_TOKENS_ACTION", action_max_tokens)
    _validate_max_tokens("LLM_MAX_TOKENS_ENEMY", enemy_max_tokens)
    _validate_max_tokens("LLM_MAX_TOKENS_NARRATION", narration_max_tokens)
    _validate_max_tokens("LLM_MAX_TOKENS_CONVERSATION", conversation_max_tokens)

    return LlmSettings(
        api_key=api_key,
        provider=provider,
        model=model,
        timeout_seconds=timeout_seconds,
        action=LlmDomainSettings(temperature=action_temperature, max_tokens=action_max_tokens),
        enemy=LlmDomainSettings(temperature=enemy_temperature, max_tokens=enemy_max_tokens),
        narration=LlmDomainSettings(temperature=narration_temperature, max_tokens=narration_max_tokens),
        conversation=LlmDomainSettings(temperature=conversation_temperature, max_tokens=conversation_max_tokens),
    )
