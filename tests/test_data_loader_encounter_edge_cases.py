import json
from pathlib import Path

import pytest

from core.data_engine.data_loader import DataLoader
from core.data_engine.json_schema_validator import JsonSchemaValidationError
from game.factories.instance_factory import InstanceFactory, SimpleInstanceIdGenerator


def _copy_data_dir(tmp_path: Path) -> Path:
    source_data_dir = Path(__file__).resolve().parents[1] / "data"
    target_data_dir = tmp_path / "data"
    target_data_dir.mkdir()

    for json_file in source_data_dir.glob("*.json"):
        (target_data_dir / json_file.name).write_text(
            json_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    source_schema_dir = source_data_dir / "schemata"
    target_schema_dir = target_data_dir / "schemata"
    target_schema_dir.mkdir()
    for schema_file in source_schema_dir.glob("*.json"):
        (target_schema_dir / schema_file.name).write_text(
            schema_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    return target_data_dir


def _load_dungeons_json(data_dir: Path) -> list[dict]:
    payload = json.loads((data_dir / "dungeons.json").read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


def _save_dungeons_json(data_dir: Path, payload: list[dict]) -> None:
    (data_dir / "dungeons.json").write_text(
        json.dumps(payload, indent=4),
        encoding="utf-8",
    )


def test_data_loader_catalog_preserves_two_or_more_encounters_in_single_room(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)
    dungeons = _load_dungeons_json(data_dir)

    first_room = dungeons[0]["rooms"][0]
    first_room["encounters"] = [
        {
            "id": "enc_gate_1",
            "name": "Gate Ambush",
            "description": "Skirmishers hide among the rubble.",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 20,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
        {
            "id": "enc_gate_2",
            "name": "Gate Reinforcement",
            "description": "A second wave arrives.",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 15,
            "enemy_ids": ["enemy_ash_wraith"],
        },
    ]
    _save_dungeons_json(data_dir, dungeons)

    catalog = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_catalog()
    dungeon = catalog.dungeon_templates["dng_ember_ruins"]
    room = dungeon.rooms[0]

    assert len(room.encounters) == 2
    assert [encounter.id for encounter in room.encounters] == ["enc_gate_1", "enc_gate_2"]


def test_data_loader_catalog_reused_enemy_id_across_encounters_keeps_template_id(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)
    dungeons = _load_dungeons_json(data_dir)

    first_room = dungeons[0]["rooms"][0]
    first_room["encounters"] = [
        {
            "id": "enc_shared_1",
            "name": "Shared One",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
        {
            "id": "enc_shared_2",
            "name": "Shared Two",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
    ]
    _save_dungeons_json(data_dir, dungeons)

    catalog = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_catalog()
    dungeon = catalog.dungeon_templates["dng_ember_ruins"]
    room = dungeon.rooms[0]

    first_enemy_id = room.encounters[0].enemy_template_ids[0]
    second_enemy_id = room.encounters[1].enemy_template_ids[0]
    assert first_enemy_id == "enemy_goblin_skirmisher"
    assert second_enemy_id == "enemy_goblin_skirmisher"


def test_data_loader_catalog_to_factory_prevents_cross_encounter_enemy_mutation_leak(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)
    dungeons = _load_dungeons_json(data_dir)

    first_room = dungeons[0]["rooms"][0]
    first_room["encounters"] = [
        {
            "id": "enc_leak_1",
            "name": "Leak One",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
        {
            "id": "enc_leak_2",
            "name": "Leak Two",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
    ]
    _save_dungeons_json(data_dir, dungeons)

    catalog = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_catalog()
    template = catalog.dungeon_templates["dng_ember_ruins"]
    dungeon = InstanceFactory.dungeon_from_template(
        template,
        catalog,
        id_gen=SimpleInstanceIdGenerator(),
    )
    room = dungeon.rooms[0]

    encounter_one_enemy = room.encounters[0].enemies[0]
    encounter_two_enemy = room.encounters[1].enemies[0]

    starting_hp = encounter_one_enemy.hp
    encounter_one_enemy.hp = max(0, starting_hp - 3)

    assert encounter_two_enemy.hp != encounter_one_enemy.hp
    assert encounter_one_enemy is not encounter_two_enemy


def test_data_loader_rejects_duplicate_enemy_id_in_single_encounter(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)
    dungeons = _load_dungeons_json(data_dir)

    dungeons[0]["rooms"][0]["encounters"][0]["enemy_ids"] = [
        "enemy_goblin_skirmisher",
        "enemy_goblin_skirmisher",
    ]
    _save_dungeons_json(data_dir, dungeons)

    with pytest.raises(JsonSchemaValidationError):
        DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_catalog()


def test_data_loader_catalog_preserves_reused_enemy_template_ids(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)
    dungeons = _load_dungeons_json(data_dir)

    first_room = dungeons[0]["rooms"][0]
    first_room["encounters"] = [
        {
            "id": "enc_template_1",
            "name": "Template One",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
        {
            "id": "enc_template_2",
            "name": "Template Two",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
    ]
    _save_dungeons_json(data_dir, dungeons)

    catalog = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_catalog()
    dungeon_template = catalog.dungeon_templates["dng_ember_ruins"]
    encounter_templates = dungeon_template.rooms[0].encounters

    assert len(encounter_templates) == 2
    assert encounter_templates[0].enemy_template_ids == ("enemy_goblin_skirmisher",)
    assert encounter_templates[1].enemy_template_ids == ("enemy_goblin_skirmisher",)


def test_data_loader_catalog_to_instance_factory_avoids_runtime_enemy_leak(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)
    dungeons = _load_dungeons_json(data_dir)

    first_room = dungeons[0]["rooms"][0]
    first_room["encounters"] = [
        {
            "id": "enc_runtime_1",
            "name": "Runtime One",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
        {
            "id": "enc_runtime_2",
            "name": "Runtime Two",
            "description": "",
            "difficulty": "easy",
            "cleared": False,
            "clear_reward": 10,
            "enemy_ids": ["enemy_goblin_skirmisher"],
        },
    ]
    _save_dungeons_json(data_dir, dungeons)

    catalog = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_catalog()
    template = catalog.dungeon_templates["dng_ember_ruins"]
    dungeon_instance = InstanceFactory.dungeon_from_template(
        template,
        catalog,
        id_gen=SimpleInstanceIdGenerator(),
    )

    enemy_a = dungeon_instance.rooms[0].encounters[0].enemies[0]
    enemy_b = dungeon_instance.rooms[0].encounters[1].enemies[0]
    before_b = enemy_b.hp
    enemy_a.hp = max(0, enemy_a.hp - 2)

    assert enemy_a is not enemy_b
    assert enemy_a.instance_id == "enemy_1"
    assert enemy_b.instance_id == "enemy_2"
    assert enemy_b.hp == before_b


def test_data_loader_legacy_hydrated_path_is_removed(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)

    loader = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata")

    with pytest.raises(RuntimeError, match="has been removed"):
        loader.load_hydrated()

    catalog = loader.load_catalog()
    assert "dng_ember_ruins" in catalog.dungeon_templates
