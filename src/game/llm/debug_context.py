import json
import os
from typing import Any, Dict


def _enabled_domains() -> set[str]:
    raw = str(os.getenv("LLM_DEBUG_CONTEXT_DOMAINS", "")).strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def should_emit(domain: str) -> bool:
    if str(os.getenv("LLM_DEBUG_CONTEXT", "")).strip() != "1":
        return False
    enabled = _enabled_domains()
    if not enabled:
        return True
    return domain.strip().lower() in enabled


def emit_context(*, domain: str, prompt_version: str, step_count: int | None, state_summary: Dict[str, Any], context_envelope: Dict[str, Any], few_shot_examples: list[Dict[str, Any]]) -> None:
    if not should_emit(domain):
        return

    payload = {
        "domain": str(domain),
        "prompt_version": str(prompt_version),
        "step_count": int(step_count or 0),
        "state_summary": dict(state_summary),
        "context_envelope": dict(context_envelope),
        "few_shot_example_count": len(few_shot_examples),
        "few_shot_sample_inputs": [
            str(example.get("input", ""))
            for example in list(few_shot_examples)[:3]
            if isinstance(example, dict)
        ],
    }
    print(f"llm_debug_context {json.dumps(payload, ensure_ascii=False)}")
