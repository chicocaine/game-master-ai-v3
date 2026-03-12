import json
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

from game.engine.interfaces import EngineContext, EventSink


@dataclass
class SessionLogSink(EventSink):
    base_dir: str = "logs/sessions"

    def _resolve_file_path(self, session_id: str) -> Path:
        directory = Path(self.base_dir)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{session_id}.jsonl"

    def publish(self, events: List[Dict[str, Any]], ctx: EngineContext) -> None:
        if not events:
            return

        file_path = self._resolve_file_path(ctx.session_id)
        with file_path.open("a", encoding="utf-8") as handle:
            for event in events:
                raw_turn_index = event.get("turn_index", ctx.step_count)
                try:
                    turn_index = int(raw_turn_index)
                except (TypeError, ValueError):
                    turn_index = int(ctx.step_count)
                payload = {
                    "session_id": ctx.session_id,
                    "step_count": ctx.step_count,
                    "turn_index": turn_index,
                    "seed": ctx.seed,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "event": dict(event),
                }
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
