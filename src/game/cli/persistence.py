from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from game.core.action import Action
from game.core.action_result import ActionResult
from game.catalog.models import Catalog
from game.engine.interfaces import EngineContext, Persistence
from game.states.game_session import GameSession


@dataclass
class JsonFilePersistence(Persistence):
    base_dir: str = "logs/checkpoints"
    catalog: Catalog | None = None

    def _resolve_file_path(self, session_id: str) -> Path:
        directory = Path(self.base_dir)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{session_id}.json"

    @staticmethod
    def _json_default(value):
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, MappingProxyType):
            return dict(value)
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        if is_dataclass(value):
            return asdict(value)
        return str(value)

    def load(self, session_id: str) -> Optional[GameSession]:
        file_path = self._resolve_file_path(session_id)
        if not file_path.exists():
            return None
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        session_payload = payload.get("session", {})
        if not isinstance(session_payload, dict):
            return None
        return GameSession.from_dict(session_payload, catalog=self.catalog)

    def _write_snapshot(
        self,
        session_id: str,
        session: GameSession,
        ctx: EngineContext,
        action: Action | None = None,
        result: ActionResult | None = None,
    ) -> Path:
        file_path = self._resolve_file_path(session_id)
        payload = {
            "session_id": session_id,
            "step_count": ctx.step_count,
            "turn_index": int(getattr(getattr(session, "encounter", None), "current_turn_index", ctx.step_count)),
            "seed": ctx.seed,
            "session": session.to_dict(),
            "last_action": action.to_dict() if action is not None else None,
            "last_result": result.to_dict() if result is not None else None,
        }
        snapshot_text = json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default)
        with NamedTemporaryFile("w", encoding="utf-8", dir=str(file_path.parent), delete=False) as handle:
            handle.write(snapshot_text)
            temp_path = Path(handle.name)
        temp_path.replace(file_path)
        return file_path

    def save_checkpoint(
        self,
        session: GameSession,
        action: Action,
        result: ActionResult,
        ctx: EngineContext,
    ) -> None:
        self._write_snapshot(ctx.session_id, session, ctx, action=action, result=result)

    def save_manual_snapshot(self, session: GameSession, ctx: EngineContext, session_id: str | None = None) -> Path:
        target_session_id = str(session_id or ctx.session_id)
        return self._write_snapshot(target_session_id, session, ctx)