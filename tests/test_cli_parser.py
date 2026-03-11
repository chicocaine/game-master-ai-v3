from game.cli.parser import parse_cli_input


def test_parse_cli_input_recognizes_commands_and_aliases() -> None:
    command = parse_cli_input("/attack atk_slash enemy_1 enemy_2")

    assert command is not None
    assert command.name == "attack"
    assert command.args == ("atk_slash", "enemy_1", "enemy_2")

    alias = parse_cli_input("/exit")
    assert alias is not None
    assert alias.name == "quit"


def test_parse_cli_input_treats_non_command_text_as_text() -> None:
    command = parse_cli_input("look around")

    assert command is not None
    assert command.name == "text"
    assert command.args == ("look around",)