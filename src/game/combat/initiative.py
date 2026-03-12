from __future__ import annotations

import random
from typing import Any, Protocol

from game.runtime.models import EncounterInstance
from game.util.dice import roll_for_initiative


class SessionForInitiative(Protocol):
    party: list[Any]
    rng: random.Random


def _initiative_modifier(actor: object) -> int:
    value = getattr(actor, "initiative_mod", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
    

def _alive_players(session: SessionForInitiative) -> list[Any]:
    return [player for player in getattr(session, "party", []) if getattr(player, "hp", 0) > 0]


def _alive_enemies(encounter: EncounterInstance) -> list[Any]:
    return [enemy for enemy in getattr(encounter, "enemies", []) if getattr(enemy, "hp", 0) > 0]


def initiate_encounter(
    session: SessionForInitiative,
    encounter: EncounterInstance,
    rng: random.Random | None = None,
) -> list[str]:
    return [row["actor_instance_id"] for row in roll_initiative_rows(session=session, encounter=encounter, rng=rng)]


def roll_initiative_rows(
    session: SessionForInitiative,
    encounter: EncounterInstance,
    rng: random.Random | None = None,
) -> list[dict[str, int | str]]:
    rng = rng or getattr(session, "rng", None) or random.Random(5)
    combatants = [
        *_alive_players(session),
        *_alive_enemies(encounter),
    ]
    initiative_rows = []
    for index, actor in enumerate(combatants):
        actor_instance_id = getattr(actor, "player_instance_id", "") or getattr(actor, "enemy_instance_id", "")
        if not actor_instance_id:
            continue
        mod = _initiative_modifier(actor)
        roll = roll_for_initiative(rng=rng)
        total = roll + mod
        initiative_rows.append(
            {
                "actor_instance_id": actor_instance_id,
                "roll": roll,
                "modifier": mod,
                "initiative": total,
                "index": index,
            }
        )
    initiative_rows.sort(key=lambda row: (-row["initiative"], row["index"]))
    return initiative_rows
