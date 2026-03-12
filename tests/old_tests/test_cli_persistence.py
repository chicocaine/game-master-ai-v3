from game.cli.persistence import JsonFilePersistence
from game.factories.game_factory import GameFactory
from game.data.data_loader import load_game_catalog
from game.engine.interfaces import EngineContext


def test_json_file_persistence_round_trip(tmp_path) -> None:
    catalog = load_game_catalog(data_dir="data", schema_dir="data/schemata")
    session = GameFactory.create_session(catalog=catalog, seed=7)
    persistence = JsonFilePersistence(base_dir=str(tmp_path), catalog=catalog)
    ctx = EngineContext(session_id="cli_test", seed=7)

    file_path = persistence.save_manual_snapshot(session, ctx)
    restored = persistence.load("cli_test")

    assert file_path.exists()
    assert restored is not None
    assert restored.state == session.state
    assert restored.available_dungeons[0].id == session.available_dungeons[0].id


def test_json_file_persistence_overwrites_with_single_file(tmp_path) -> None:
    catalog = load_game_catalog(data_dir="data", schema_dir="data/schemata")
    session = GameFactory.create_session(catalog=catalog, seed=11)
    persistence = JsonFilePersistence(base_dir=str(tmp_path), catalog=catalog)
    ctx = EngineContext(session_id="cli_test", seed=11)

    first_path = persistence.save_manual_snapshot(session, ctx)
    second_path = persistence.save_manual_snapshot(session, ctx)

    assert first_path.exists()
    assert second_path.exists()
    assert first_path == second_path
    assert sorted(path.name for path in tmp_path.iterdir()) == ["cli_test.json"]