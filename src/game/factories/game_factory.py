from __future__ import annotations

from copy import deepcopy
from random import Random
from typing import Iterable

from game.actors.player import Player
from game.catalog.models import Catalog
from game.enums import GameState
from game.states.game_session import GameSession


class GameFactory:
    @staticmethod
    def _assign_player_instance_ids(players: Iterable[Player]) -> list[Player]:
        assigned: list[Player] = []
        for index, player in enumerate(players, start=1):
            cloned = deepcopy(player)
            if not getattr(cloned, "player_instance_id", ""):
                cloned.player_instance_id = f"player_{index}"
            assigned.append(cloned)
        return assigned

    @classmethod
    def create_session(
        cls,
        catalog: Catalog,
        selected_dungeon_id: str | None = None,
        party: Iterable[Player] | None = None,
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
