from __future__ import annotations

from copy import deepcopy
from random import Random
from pathlib import Path
from typing import Iterable

from core.data_engine.data_loader import load_game_catalog
from game.actors.player import PlayerInstance
from game.catalog.models import Catalog
from game.enums import GameState
from game.states.game_session import GameSession


class GameFactory:
    @classmethod
    def create_session_from_data_dir(
        cls,
        data_dir: Path | str,
        schema_dir: Path | str | None = None,
        selected_dungeon_id: str | None = None,
        party: Iterable[PlayerInstance] | None = None,
        seed: int = 5,
        validate_schema: bool = True,
    ) -> GameSession:
        catalog = load_game_catalog(
            data_dir=data_dir,
            schema_dir=schema_dir,
            validate_schema=validate_schema,
        )
        return cls.create_session(
            catalog=catalog,
            selected_dungeon_id=selected_dungeon_id,
            party=party,
            seed=seed,
        )

    @staticmethod
    def _assign_player_instance_ids(players: Iterable[PlayerInstance]) -> list[PlayerInstance]:
        assigned: list[PlayerInstance] = []
        used_ids: set[str] = set()
        for index, player in enumerate(players, start=1):
            cloned = deepcopy(player)
            existing_id = str(getattr(cloned, "player_instance_id", "") or "")
            if not existing_id or existing_id in used_ids:
                existing_id = f"player_{index}"
                while existing_id in used_ids:
                    index += 1
                    existing_id = f"player_{index}"
                cloned.player_instance_id = existing_id
            used_ids.add(existing_id)
            assigned.append(cloned)
        return assigned

    @classmethod
    def create_session(
        cls,
        catalog: Catalog,
        selected_dungeon_id: str | None = None,
        party: Iterable[PlayerInstance] | None = None,
        seed: int = 5,
    ) -> GameSession:
        session = GameSession()
        session.catalog = catalog
        session.available_dungeons = list(catalog.dungeon_templates.values())
        session.party = cls._assign_player_instance_ids(party or [])
        session.rng = Random(seed)

        if selected_dungeon_id:
            template = catalog.dungeon_templates.get(selected_dungeon_id)
            if template is None:
                raise ValueError(f"Dungeon template '{selected_dungeon_id}' was not found in catalog.")
            session.dungeon = session.instantiate_dungeon_template(template)
            start_room = next(
                (room for room in session.dungeon.rooms if room.id == session.dungeon.start_room),
                None,
            )
            session.exploration.current_room = start_room
            if start_room is not None and session.party:
                session.state = GameState.EXPLORATION

        return session
