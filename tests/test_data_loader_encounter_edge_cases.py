import json
from pathlib import Path

import pytest

from core.data_engine.data_loader import DataLoader
from core.data_engine.json_schema_validator import JsonSchemaValidationError


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


def test_data_loader_hydrates_two_or_more_encounters_in_single_room(tmp_path: Path) -> None:
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

    hydrated = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_hydrated()
    dungeon = hydrated["dungeons"]["dng_ember_ruins"]
    room = dungeon.rooms[0]

    assert len(room.encounters) == 2
    assert [encounter.id for encounter in room.encounters] == ["enc_gate_1", "enc_gate_2"]


def test_data_loader_reused_enemy_id_across_encounters_reuses_enemy_instance(tmp_path: Path) -> None:
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

    hydrated = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_hydrated()
    dungeon = hydrated["dungeons"]["dng_ember_ruins"]
    room = dungeon.rooms[0]

    first_enemy = room.encounters[0].enemies[0]
    second_enemy = room.encounters[1].enemies[0]
    assert first_enemy.id == "enemy_goblin_skirmisher"
    assert second_enemy.id == "enemy_goblin_skirmisher"
    assert first_enemy is second_enemy


def test_data_loader_reused_enemy_mutation_leaks_between_encounters(tmp_path: Path) -> None:
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

    hydrated = DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_hydrated()
    dungeon = hydrated["dungeons"]["dng_ember_ruins"]
    room = dungeon.rooms[0]

    encounter_one_enemy = room.encounters[0].enemies[0]
    encounter_two_enemy = room.encounters[1].enemies[0]

    starting_hp = encounter_one_enemy.hp
    encounter_one_enemy.hp = max(0, starting_hp - 3)

    assert encounter_two_enemy.hp == encounter_one_enemy.hp
    assert encounter_one_enemy is encounter_two_enemy


def test_data_loader_rejects_duplicate_enemy_id_in_single_encounter(tmp_path: Path) -> None:
    data_dir = _copy_data_dir(tmp_path)
    dungeons = _load_dungeons_json(data_dir)

    dungeons[0]["rooms"][0]["encounters"][0]["enemy_ids"] = [
        "enemy_goblin_skirmisher",
        "enemy_goblin_skirmisher",
    ]
    _save_dungeons_json(data_dir, dungeons)

    with pytest.raises(JsonSchemaValidationError):
        DataLoader(data_dir=data_dir, schema_dir=data_dir / "schemata").load_hydrated()
