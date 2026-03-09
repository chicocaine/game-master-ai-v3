from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from game.catalog.models import Catalog, DungeonTemplate, EncounterTemplate, EnemyTemplate, RoomTemplate
from game.runtime.models import DungeonInstance, EncounterInstance, EnemyInstance, RoomInstance


@dataclass
class SimpleInstanceIdGenerator:
    counters: Dict[str, int] = field(default_factory=dict)

    def next(self, prefix: str) -> str:
        # Keep ids short and LLM-friendly: enemy_1, encounter_2, room_3.
        next_value = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = next_value
        return f"{prefix}_{next_value}"


class InstanceFactory:
    @staticmethod
    def enemy_from_template(template: EnemyTemplate, id_gen: SimpleInstanceIdGenerator) -> EnemyInstance:
        base = template.instantiate_enemy()
        enemy_instance_id = id_gen.next("enemy")
        base.enemy_instance_id = enemy_instance_id
        return EnemyInstance(
            template_id=template.id,
            instance_id=enemy_instance_id,
            enemy=base,
        )

    @classmethod
    def encounter_from_template(
        cls,
        template: EncounterTemplate,
        catalog: Catalog,
        id_gen: SimpleInstanceIdGenerator,
    ) -> EncounterInstance:
        enemies = [
            cls.enemy_from_template(catalog.enemy_templates[enemy_template_id], id_gen)
            for enemy_template_id in template.enemy_template_ids
        ]
        return EncounterInstance(
            template_id=template.id,
            instance_id=id_gen.next("encounter"),
            name=template.name,
            description=template.description,
            difficulty=template.difficulty,
            clear_reward=template.clear_reward,
            enemies=enemies,
        )

    @classmethod
    def room_from_template(
        cls,
        template: RoomTemplate,
        catalog: Catalog,
        id_gen: SimpleInstanceIdGenerator,
    ) -> RoomInstance:
        encounters = [
            cls.encounter_from_template(encounter_template, catalog, id_gen)
            for encounter_template in template.encounters
        ]
        return RoomInstance(
            template_id=template.id,
            instance_id=id_gen.next("room"),
            name=template.name,
            description=template.description,
            connections=list(template.connections),
            encounters=encounters,
            allowed_rests=list(template.allowed_rests),
            is_cleared=len(encounters) == 0,
        )

    @classmethod
    def dungeon_from_template(
        cls,
        template: DungeonTemplate,
        catalog: Catalog,
        id_gen: SimpleInstanceIdGenerator | None = None,
    ) -> DungeonInstance:
        id_gen = id_gen or SimpleInstanceIdGenerator()
        rooms = [cls.room_from_template(room_template, catalog, id_gen) for room_template in template.rooms]
        return DungeonInstance(
            template_id=template.id,
            instance_id=id_gen.next("dungeon"),
            name=template.name,
            description=template.description,
            difficulty=template.difficulty,
            start_room=template.start_room,
            end_room=template.end_room,
            rooms=rooms,
        )
