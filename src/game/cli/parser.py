from __future__ import annotations

import shlex
from dataclasses import dataclass


COMMAND_ALIASES = {
    "exit": "quit",
    "p": "party",
    "h": "help",
}


@dataclass(frozen=True)
class CliCommand:
    name: str
    args: tuple[str, ...] = ()
    raw: str = ""


def parse_cli_input(raw_text: str) -> CliCommand | None:
    text = str(raw_text or "").strip()
    if not text:
        return None

    if not text.startswith("/"):
        return CliCommand(name="text", args=(text,), raw=text)

    command_text = text[1:].strip()
    if not command_text:
        return CliCommand(name="help", raw=text)

    try:
        parts = shlex.split(command_text)
    except ValueError as exc:
        raise ValueError(f"Invalid command syntax: {exc}") from exc

    if not parts:
        return CliCommand(name="help", raw=text)

    command_name = COMMAND_ALIASES.get(parts[0].lower(), parts[0].lower())
    return CliCommand(name=command_name, args=tuple(parts[1:]), raw=text)