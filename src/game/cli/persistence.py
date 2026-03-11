from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.action import Action
from core.action_result import ActionResult
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
            "turn_index": ctx.turn_index,
            "seed": ctx.seed,
            "session": session.to_dict(),
            "last_action": action.to_dict() if action is not None else None,
            "last_result": result.to_dict() if result is not None else None,
        }
        file_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
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