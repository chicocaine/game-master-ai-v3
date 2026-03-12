from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from game.core.action import Action, create_action
from game.core.enums import ActionType
from game.cli.parser import CliCommand, parse_cli_input
from game.cli.persistence import JsonFilePersistence
from game.cli.renderer import (
    render_dungeons,
    render_encounter,
    render_help,
    render_message,
    render_party,
    render_player_templates,
    render_room,
    render_state,
)
from game.cli.session_view import current_actor_id
from game.engine.interfaces import ActionProvider, EngineContext
from game.enums import GameState, RestType
from game.llm.providers.player_intent_provider import PlayerIntentLlmProvider


OutputFn = Callable[[str], None]
InputFn = Callable[[str], str]


@dataclass
class InteractiveCliProvider(ActionProvider):
    input_fn: InputFn
    output_fn: OutputFn
    persistence: JsonFilePersistence
    debug: bool = False
    prompt: str = "gm> "
    quit_requested: bool = False
    requested_load_session_id: str | None = None
    restart_requested: bool = False
    _last_error: str = field(default="", init=False)

    def pop_load_request(self) -> str | None:
        requested = self.requested_load_session_id
        self.requested_load_session_id = None
        return requested

    def pop_restart_request(self) -> bool:
        requested = bool(self.restart_requested)
        self.restart_requested = False
        return requested

    def next_action(self, session, ctx: EngineContext) -> Action | None:
        while True:
            if self._last_error:
                self.output_fn(self._last_error)
                self._last_error = ""

            try:
                raw_text = self.input_fn(self.prompt)
            except (EOFError, StopIteration):
                self.quit_requested = True
                return None

            command_text = str(raw_text or "").strip()
            if not command_text:
                continue

            try:
                command = parse_cli_input(command_text)
            except ValueError as exc:
                self.output_fn(str(exc))
                continue

            if command is None:
                continue

            action = self._handle_command(session, ctx, command)
            if action is not None:
                return action
            if self.quit_requested or self.requested_load_session_id is not None or self.restart_requested:
                return None

    def _handle_command(self, session, ctx: EngineContext, command: CliCommand) -> Action | None:
        if command.name == "text":
            self.output_fn("Deterministic CLI mode expects slash commands. Use /help.")
            return None
        if command.name == "help":
            self.output_fn(render_help())
            return None
        if command.name == "state":
            self.output_fn(render_state(session))
            return None
        if command.name == "party":
            self.output_fn(render_party(session))
            return None
        if command.name == "players":
            catalog = getattr(session, "catalog", None)
            self.output_fn(render_player_templates(catalog) if catalog is not None else "Catalog unavailable.")
            return None
        if command.name == "dungeons":
            self.output_fn(render_dungeons(session))
            return None
        if command.name == "room":
            self.output_fn(render_room(session))
            return None
        if command.name == "encounter":
            self.output_fn(render_encounter(session))
            return None
        if command.name == "save":
            target_session_id = command.args[0] if command.args else ctx.session_id
            file_path = self.persistence.save_manual_snapshot(session, ctx, session_id=target_session_id)
            self.output_fn(render_message(f"Saved session to {file_path.resolve()}"))
            return None
        if command.name == "load":
            if not command.args:
                self.output_fn("Usage: /load <session_id>")
                return None
            self.requested_load_session_id = command.args[0]
            return None
        if command.name == "quit":
            self.quit_requested = True
            return None
        if command.name == "restart":
            self.restart_requested = True
            return None
        if command.name == "add":
            return self._build_add_player_action(session, command)
        if command.name == "choose":
            return self._build_system_action(ActionType.CHOOSE_DUNGEON, {"dungeon": command.args[0]} if command.args else None)
        if command.name == "start":
            return self._build_system_action(ActionType.START, {})
        if command.name == "move":
            return self._build_exploration_action(session, ActionType.MOVE, command)
        if command.name == "rest":
            return self._build_exploration_action(session, ActionType.REST, command)
        if command.name == "attack":
            return self._build_encounter_action(session, ActionType.ATTACK, command)
        if command.name == "cast":
            return self._build_encounter_action(session, ActionType.CAST_SPELL, command)
        if command.name == "end":
            return self._build_encounter_action(session, ActionType.END_TURN, command)

        self.output_fn(f"Unknown command '{command.name}'. Use /help.")
        return None

    def _build_system_action(self, action_type: ActionType, parameters: dict | None) -> Action:
        return create_action(action_type=action_type, parameters=parameters or {}, actor_instance_id="system")

    def _build_add_player_action(self, session, command: CliCommand) -> Action | None:
        if not command.args:
            self.output_fn("Usage: /add <player_template_id>")
            return None
        catalog = getattr(session, "catalog", None)
        if catalog is None or command.args[0] not in catalog.player_templates:
            self.output_fn(f"Unknown player template '{command.args[0]}'.")
            return None
        player = catalog.player_templates[command.args[0]].instantiate_player()
        return create_action(
            action_type=ActionType.CREATE_PLAYER,
            actor_instance_id="system",
            parameters={
                "id": player.id,
                "name": player.name,
                "description": player.description,
                "race": player.race,
                "archetype": player.archetype,
                "weapons": list(player.weapons),
            },
        )

    def _build_exploration_action(self, session, action_type: ActionType, command: CliCommand) -> Action | None:
        if session.state is not GameState.EXPLORATION:
            self.output_fn("This command is only available during exploration.")
            return None
        actor_instance_id = session.party[0].player_instance_id if session.party else "system"
        if action_type is ActionType.MOVE:
            if not command.args:
                self.output_fn("Usage: /move <room_id>")
                return None
            return create_action(action_type, {"destination_room_id": command.args[0]}, actor_instance_id=actor_instance_id)
        if action_type is ActionType.REST:
            if not command.args:
                self.output_fn("Usage: /rest <short|long>")
                return None
            try:
                rest_type = RestType(command.args[0].lower())
            except ValueError:
                self.output_fn("Rest type must be 'short' or 'long'.")
                return None
            return create_action(action_type, {"rest_type": rest_type.value}, actor_instance_id=actor_instance_id)
        return None

    def _build_encounter_action(self, session, action_type: ActionType, command: CliCommand) -> Action | None:
        if session.state is not GameState.ENCOUNTER:
            self.output_fn("This command is only available during encounters.")
            return None
        actor_instance_id = current_actor_id(session)
        if not actor_instance_id.startswith("player_"):
            self.output_fn("It is not a player turn.")
            return None

        if action_type is ActionType.END_TURN:
            return create_action(action_type, {}, actor_instance_id=actor_instance_id)

        if len(command.args) < 2:
            usage = "/attack <attack_id> <target_id> [more_target_ids...]" if action_type is ActionType.ATTACK else "/cast <spell_id> <target_id> [more_target_ids...]"
            self.output_fn(f"Usage: {usage}")
            return None

        key = "attack_id" if action_type is ActionType.ATTACK else "spell_id"
        raw_targets = list(command.args[1:])
        target_value: list[str] | str = raw_targets if len(raw_targets) > 1 else raw_targets[0]
        return create_action(
            action_type,
            {key: command.args[0], "target_instance_ids": target_value},
            actor_instance_id=actor_instance_id,
        )


@dataclass
class LiveLlmCliProvider(InteractiveCliProvider):
    player_provider: PlayerIntentLlmProvider | None = None
    prompt: str = "gm(llm)> "

    def _active_player_actor_id(self, session) -> str:
        if session.state is GameState.ENCOUNTER:
            actor_instance_id = current_actor_id(session)
            if actor_instance_id.startswith("player_"):
                return actor_instance_id
            return ""
        if session.party:
            return session.party[0].player_instance_id
        return "system"

    def next_action(self, session, ctx: EngineContext) -> Action | None:
        if self.player_provider is None:
            self.output_fn("Live LLM mode is not configured.")
            self.quit_requested = True
            return None

        while True:
            if self._last_error:
                self.output_fn(self._last_error)
                self._last_error = ""

            actor_instance_id = self._active_player_actor_id(session)
            if session.state is GameState.ENCOUNTER and not actor_instance_id:
                # Enemy/provider automation should run when this is not a player turn.
                return None

            try:
                raw_text = self.input_fn(self.prompt)
            except (EOFError, StopIteration):
                self.quit_requested = True
                return None

            command_text = str(raw_text or "").strip()
            if not command_text:
                continue

            try:
                command = parse_cli_input(command_text)
            except ValueError as exc:
                self.output_fn(str(exc))
                continue

            if command is None:
                continue

            if command.name == "text":
                self.player_provider.enqueue(
                    command.args[0],
                    actor_instance_id=actor_instance_id,
                    metadata={"source": "cli_live_llm", "session_id": ctx.session_id},
                )
                action = self.player_provider.next_action(session, ctx)
                if action is not None:
                    return action
                self.output_fn("The action parser could not resolve that input. Try rephrasing.")
                continue

            action = self._handle_command(session, ctx, command)
            if action is not None:
                return action
            if self.quit_requested or self.requested_load_session_id is not None or self.restart_requested:
                return None