from game.cli.app import run_cli


def test_run_cli_supports_basic_pregame_flow() -> None:
    inputs = iter([
        "/players",
        "/add player_lyra",
        "/choose dng_ember_ruins",
        "/start",
        "/quit",
    ])
    output: list[str] = []

    exit_code = run_cli(
        data_dir="data",
        schema_dir="data/schemata",
        input_fn=lambda prompt: next(inputs),
        output_fn=output.append,
        seed=5,
    )

    joined = "\n".join(output)
    assert exit_code == 0
    assert "CLI engine ready." in joined
    assert "Player templates:" in joined
    assert "Selected dungeon: dng_ember_ruins" in joined
    assert "State: exploration" in joined or "Encounter started." in joined