# Game Master AI

Game Master AI is a Python dungeon crawler and turn-based game engine built around a deterministic state machine, schema-validated JSON content, and an LLM designed to act like the game master. The core runtime owns authoritative session state and game rules, while the LLM handles bounded game-master duties such as interpreting player intent, narrating events, carrying conversation, and directing enemy behavior.

## Architecture

The project is organized as a layered application:

1. Data layer: game content is stored in JSON datasets and validated against JSON Schema definitions before runtime use.
2. Domain layer: entities, combat rules, session states, actions, and events define the game mechanics.
3. Runtime layer: the engine loop orchestrates action resolution, state transitions, event publication, and persistence.
4. Interface layer: the CLI and Gradio UI present the same underlying session model through different interaction surfaces.
5. LLM layer: optional providers handle bounded tasks with strict domain separation.

The LLM responsibilities are intentionally split:

- Intent parser: converts player text into a structured action proposal.
- Narrator: turns resolved game events into short contextual narration.
- Converse: generates direct dialogue responses for conversational branches.
- Enemy LLM: selects bounded tactical actions for enemy turns during encounters.

The runtime is designed so that LLM output is advisory rather than authoritative. Deterministic code validates actions, applies mechanics, and mutates state.

## Runtime Surfaces

- `main.py` starts the CLI engine.
- `run_gradio.py` starts the browser UI.
- `data/` contains the authored game content and schemas.
- `logs/` stores checkpoints, event traces, and session artifacts.
- `src/game/` contains the engine, combat logic, session states, LLM adapters, and persistence helpers.

## Stack

- Python 3
- Gradio for the web UI
- `jsonschema` for validating content against JSON Schemas
- `python-dotenv` for environment configuration
- `pytest` for automated testing
- JSON datasets and JSON Schema files for dungeons, enemies, players, weapons, spells, status effects, races, archetypes, and attacks

