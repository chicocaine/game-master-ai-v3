# ACM Project Documentation

## Abstract
GameMasterAI is a hybrid game-management system for a text-based, turn-based dungeon crawler. The project addresses a practical problem in AI-assisted interactive systems: natural language is flexible and expressive, but game logic requires deterministic rule enforcement. To solve this, the system separates language understanding from state execution. Large language models (LLMs) are used only for bounded tasks such as player-intent parsing, enemy decision support, narration, and conversational responses, while a deterministic Python rule engine owns all authoritative game state transitions.

The implementation uses schema-validated JSON data, explicit action and event contracts, a modular session state machine, and persistent checkpoint and event logs. The engine supports both a command-line interface and a Gradio-based web interface. When live LLM mode is disabled, the game still runs deterministically using local logic and stub providers. When live LLM mode is enabled, OpenAI-compatible chat completions are used behind strict response schemas and fallback paths.

The resulting prototype demonstrates that LLMs can be integrated into a rule-bound environment without giving them direct control over game state. This is useful not only for games, but also for broader software systems where natural language interaction must remain auditable, bounded, and reproducible.

**Keywords:** large language models, rule-based systems, game AI, structured output, deterministic state machines, prompt engineering, turn-based systems

## 1 Introduction

### 1.1 Background
Natural language interfaces are attractive because they let users communicate in a way that feels flexible and intuitive. In games, this can improve immersion by allowing players to describe what they want to do rather than selecting from rigid menu commands. However, most game systems require exact rules for combat, movement, targeting, status effects, and win or loss conditions. A purely generative model is not reliable enough to enforce those rules on its own.

GameMasterAI is designed around that tension. Instead of asking an LLM to run the entire game, the project uses a hybrid architecture. The LLM interprets or enriches language-facing tasks, while a deterministic engine validates actions, applies mechanics, updates state, and emits auditable events.

### 1.2 Problem Context
The central challenge is balancing natural language freedom with strict runtime correctness. If the model directly edits the game world, it can hallucinate entities, violate turn order, ignore required parameters, or create outcomes that do not match the rules. If the system is fully deterministic but accepts only rigid commands, it loses the value of natural language interaction.

This project treats the LLM as a bounded subsystem rather than a game master with full authority. The LLM can suggest or narrate, but the engine decides what is valid.

### 1.3 Overview of the System
At runtime, the system accepts player input from either the CLI or the Gradio interface. In deterministic mode, slash commands and text are mapped directly to engine actions. In live LLM mode, the player input is routed to a player-intent provider that produces a structured action proposal. That proposal is validated against the current game state and then executed by the session engine. The engine emits events, updates the state, and optionally forwards the resulting event stream to a narrator or conversation responder.

The architecture therefore has four clear layers:

1. Data layer: JSON content files and JSON Schemas.
2. Domain layer: entities, combat rules, actions, events, and state transitions.
3. Orchestration layer: engine loop, providers, persistence, telemetry, and sinks.
4. Interface layer: CLI and Gradio UI.

### 1.4 Importance of the Study
This work is relevant beyond games. Many software systems need natural language interaction without surrendering deterministic control. Examples include AI copilots, workflow agents, tutoring systems, and simulation platforms. GameMasterAI serves as a compact, inspectable case study for how to combine probabilistic interpretation with rule-based execution.

### 1.5 Objectives

#### 1.5.1 General Objective
To design and implement a rule-constrained AI agent that interprets natural language commands and manages a deterministic, turn-based dungeon crawler using structured state control.

#### 1.5.2 Specific Objectives
1. To define structured data contracts for players, enemies, dungeons, actions, and events.
2. To implement deterministic combat resolution, initiative handling, and status effect processing.
3. To support natural language interaction through bounded LLM providers.
4. To validate all player and enemy actions before state mutation.
5. To support both deterministic and live-LLM execution paths.
6. To persist checkpoints and event logs for replay and inspection.
7. To evaluate the system using automated tests and manual play sessions.

## 2 Methodology

### 2.1 System Design Overview
The project uses a hybrid AI architecture. All authoritative game state is stored in Python domain objects under the session model. All content is loaded from JSON datasets and validated against JSON Schemas before play begins. The engine loop resolves the next action from a provider chain, executes that action through the session state machine, publishes emitted events, saves a checkpoint, and advances the step counter.

The system is intentionally designed so that LLM output is always intermediate. It never becomes authoritative until it is parsed, normalized, validated, and accepted by deterministic rules.

### 2.2 Tools and Technology
The implementation stack is lightweight and intentionally modular.

| Category | Technology | Purpose |
| --- | --- | --- |
| Programming language | Python | Core implementation language |
| Data validation | jsonschema | Validation of game datasets against formal schemas |
| Testing | pytest | Automated unit and regression testing |
| Environment loading | python-dotenv | Local configuration via `.env` |
| UI | Gradio | Browser-based interface for the game |
| LLM access | OpenAI-compatible chat completions over HTTP | Intent parsing, enemy AI, narration, converse |
| Persistence | JSON and JSONL files | Checkpoints, logs, telemetry |

### 2.3 Data Sources
The project uses repository-local handcrafted data rather than an external database. The main datasets live under `data/` and include:

1. `players.json`
2. `enemies.json`
3. `dungeons.json`
4. `attacks.json`
5. `spells.json`
6. `weapons.json`
7. `races.json`
8. `archetypes.json`
9. `status_effects.json`

Each dataset has a matching schema under `data/schemata/`. The loader validates both dataset structure and cross-file references, such as attack-to-status-effect links, enemy references inside encounters, and room connectivity inside dungeons.

### 2.4 Prompt Engineering Strategy
Prompting is divided by domain so each model call has one narrow responsibility.

| LLM Domain | Role | Output Type |
| --- | --- | --- |
| Player intent | Interpret user input into a legal action proposal | Structured action JSON |
| Enemy AI | Select a tactical combat action for the active enemy | Structured action JSON |
| Narration | Turn event batches into short atmospheric text | Narration JSON |
| Converse | Produce in-world or system-guided replies | Reply JSON |

The prompt pipeline uses the following controls:

1. System instructions specify scope and output restrictions.
2. Response schemas require machine-readable JSON.
3. Context envelopes provide only recent, relevant state and event information.
4. Token budgeting prunes context deterministically before sending requests.
5. Few-shot examples are selected per domain and budget-limited.
6. Invalid or incomplete model outputs fall back to safe deterministic behavior.

This design reduces hallucination risk and keeps the language model aligned to the current game state.

### 2.5 Model Configuration
The LLM layer is configurable through environment variables. The default provider is OpenAI-compatible and the default model is `gpt-4.1-mini`. The system supports per-domain settings for temperature and token limits so action parsing, enemy behavior, narration, and conversation can be tuned independently.

Representative configuration variables include:

1. `LLM_PROVIDER`
2. `LLM_MODEL`
3. `LLM_API_KEY`
4. `LLM_TIMEOUT_SECONDS`
5. `LLM_TEMPERATURE_ACTION`
6. `LLM_TEMPERATURE_ENEMY`
7. `LLM_TEMPERATURE_NARRATION`
8. `LLM_TEMPERATURE_CONVERSATION`

This supports both real API-backed execution and a mock mode for local development.

### 2.6 Testing Procedure
Testing combines automated verification and manual playthroughs.

Automated testing is implemented with `pytest` and covers:

1. Schema validation and data loading.
2. Game session serialization and restoration.
3. Pregame, exploration, encounter, and postgame state transitions.
4. Combat resolution, damage modifiers, spell logic, and status effects.
5. Engine loop behavior, event sinks, and persistence retries.
6. LLM configuration, parsing contracts, context construction, fallback logic, and telemetry.
7. CLI orchestration and live-LLM routing behavior.

Manual testing supplements the unit tests by checking usability, narrative quality, interface flow, and edge cases discovered during actual gameplay sessions.

### 2.7 Evaluation Metrics
The project is evaluated using practical engineering metrics rather than a single benchmark score.

| Metric | Meaning in This Project |
| --- | --- |
| Correctness | Actions follow game rules and valid state transitions |
| Determinism | Same inputs and seed produce reproducible engine behavior where LLMs are not involved |
| Validation coverage | Invalid content or malformed actions are rejected early |
| Graceful degradation | The system remains usable when LLM calls fail or are disabled |
| Traceability | Events, checkpoints, and telemetry make decisions inspectable |
| Playability | Users can complete setup, exploration, and combat through the provided interfaces |

### 2.8 Design Rationale
Several architectural choices were deliberate:

1. JSON content plus JSON Schema was preferred over a database to keep the prototype portable and inspectable.
2. A state-machine session model was used to make legal actions explicit by phase.
3. LLMs were isolated into providers so failures do not corrupt the core engine.
4. Event logging and checkpointing were added to support debugging and replay.
5. Simple runtime instance IDs such as `player_1` and `enemy_1` were used to make LLM targeting easier and more reliable.

## 3 System Design and Architecture

### 3.1 Architectural Design Principles
The project follows five principles:

1. Deterministic state ownership: only the engine mutates the game state.
2. Structured boundaries: data, actions, and events all have explicit shapes.
3. Fail-safe orchestration: provider, sink, and narrator failures are isolated where possible.
4. Interface separation: CLI and Gradio are views over the same engine.
5. Auditable behavior: logs, checkpoints, and telemetry capture what happened and why.

### 3.2 System Architecture

```text
Player Input (CLI or Gradio)
                |
                v
Action Provider Layer
    - CLI parser / direct commands
    - Player intent LLM provider
    - Enemy stub or enemy LLM provider
                |
                v
Deterministic Engine Loop
    - resolve next action
    - validate action
    - execute through GameSession
    - emit events
    - save checkpoint
                |
                +--> Event Sinks (in-memory, session log)
                +--> Narrator / Converse responders
                |
                v
Updated Session State
    - pregame
    - exploration
    - encounter
    - postgame
```

At the center of the architecture is `GameSession`, which delegates behavior to phase-specific state handlers. The engine loop is intentionally generic and does not contain game-specific business rules. This keeps orchestration separate from domain logic.

### 3.3 Core Components

| Component | Responsibility |
| --- | --- |
| DataLoader and JsonSchemaValidator | Load content and reject invalid or inconsistent datasets |
| Catalog and runtime models | Separate reusable templates from mutable in-session instances |
| GameFactory | Build a new session from the validated catalog |
| GameSession | Own authoritative state and action routing |
| Pregame, Exploration, Encounter, Postgame states | Enforce rules that are specific to each phase |
| Combat modules | Resolve attacks, spells, initiative, and status effects |
| Engine loop | Orchestrate provider polling, event publishing, and checkpointing |
| Event sinks | Persist or expose emitted events |
| CLI and Gradio runtime | Present the system to end users |
| LLM providers | Interpret, narrate, or converse within strict boundaries |

### 3.4 Data Flow Architecture
The runtime data flow can be described as a closed loop:

1. The interface receives player input.
2. The provider layer converts that input into an `Action` object or returns no action.
3. The engine loop sends the action to `GameSession.handle_action()`.
4. The session validates the action and delegates execution to the active state handler.
5. The state handler mutates runtime objects and returns an `ActionResult`.
6. The engine publishes emitted events to configured sinks.
7. Persistence stores a checkpoint snapshot.
8. Optional LLM narrator or converse layers generate user-facing text from the event or action context.
9. The interface renders the new state to the user.

This loop is intentionally step-oriented. In the CLI and Gradio versions, each resolved action corresponds to one engine step, making the system easier to trace and debug.

### 3.5 Component Interaction Matrix

| Source Component | Target Component | Interaction |
| --- | --- | --- |
| UI layer | Provider layer | Collects user input and submits it for parsing |
| Provider layer | Engine loop | Supplies the next action |
| Engine loop | GameSession | Executes validated actions |
| GameSession | State handlers | Routes action based on current phase |
| State handlers | Combat modules | Resolve attacks, spells, turn effects, and outcomes |
| GameSession | Event sinks | Publishes lifecycle and gameplay events |
| Engine loop | Persistence | Saves checkpoints after each action |
| Engine loop | LLM narration/converse | Converts event sequences into user-facing language |
| Data layer | GameFactory | Provides templates for session initialization |

### 3.6 Agent Decision Architecture (Enemy AI)
Enemy behavior is also treated as a bounded-agent problem. The enemy provider only becomes active during encounter state and only for the enemy whose turn is currently active. It receives:

1. A compact combat summary.
2. The current enemy identifier.
3. A legal action space containing attack IDs, spell options, and valid targets.
4. A short recent decision history.

The provider returns one of three allowed actions: `attack`, `cast_spell`, or `end_turn`. If the model output is invalid, the system falls back to a safe deterministic action, usually a simple attack on a legal target or `end_turn` if no valid target exists. This keeps enemy AI expressive without compromising the encounter state.

## 4 Implementation Details

### 4.1 Backend Framework
The project does not use a traditional backend framework such as FastAPI or Django. Instead, it is implemented as a modular Python application. The core logic is framework-independent and can be launched in two ways:

1. `main.py` for CLI execution.
2. `run_gradio.py` for the browser-based Gradio interface.

This design keeps the engine reusable and avoids coupling domain logic to a web framework.

### 4.2 Frontend
The frontend is provided by Gradio. The interface uses a three-column layout:

1. Event, action, and reasoning streams.
2. Chat interaction panel.
3. State summary blocks that change based on the current game phase.

The Gradio app stores runtime state per browser tab and processes one engine step per user submission. This makes the web interface consistent with the underlying turn-based engine.

### 4.3 Database Used
No relational or document database is used. Instead, the system uses files for persistence:

1. JSON content datasets under `data/`.
2. JSON checkpoint snapshots under `logs/checkpoints/`.
3. JSONL session event logs under `logs/sessions/`.
4. JSONL telemetry and event traces under `logs/events/`.

For a prototype of this scope, file-based persistence is sufficient and makes debugging easier.

### 4.4 LLM Integration Details
LLM calls are implemented through an OpenAI-compatible chat completions client. The client builds HTTP requests using model name, system and user messages, temperature, token limits, timeout, and optional JSON Schema response formats.

Integration safeguards include:

1. Retry handling for transport and timeout failures.
2. Structured JSON parsing and validation.
3. Fallback routes for malformed or disallowed outputs.
4. Telemetry emission for requests, failures, and fallback reasons.
5. Domain separation so one prompt is not reused for every task.

The system can also run in mock mode, which is useful for development and testing without live API calls.

### 4.5 API Endpoints Overview
There is no internal REST API in the current implementation. The local interfaces interact with the engine directly in process. The only external API dependency is the OpenAI-compatible HTTP endpoint used for LLM requests when live mode is enabled.

### 4.6 Deployment Setup
The project is designed primarily for local execution.

Typical workflow:

1. Install Python dependencies from `requirements.txt`.
2. Configure environment variables in `.env` if live LLM mode is needed.
3. Launch the CLI with `python main.py --cli`.
4. Launch the web interface with `python run_gradio.py`.

No Docker or cloud deployment configuration is currently required by the repository, although the modular design would allow those options later.

### 4.7 High-Level Code Structure

| Path | Purpose |
| --- | --- |
| `src/game/data` | JSON loading and schema validation |
| `src/game/catalog` | Immutable template-oriented catalog models |
| `src/game/runtime` | Mutable runtime instances used during play |
| `src/game/states` | Pregame, exploration, encounter, and postgame handlers |
| `src/game/combat` | Combat mechanics, initiative, attacks, spells, status effects |
| `src/game/core` | Actions, action results, events, and enums |
| `src/game/engine` | Loop, interfaces, providers, and sinks |
| `src/game/llm` | Clients, prompts, routing, telemetry, narration, and providers |
| `src/game/cli` | CLI bootstrap, rendering, parsing, persistence, session view |
| `src/ui` | Gradio bootstrap, step orchestration, and UI layout |

### 4.8 Key Modules and Responsibilities
Some modules are especially central to the system:

1. `game_session.py` owns state transitions and action routing.
2. `encounter.py` enforces turn order, combat actions, and end-of-turn processing.
3. `data_loader.py` validates cross-file references before gameplay begins.
4. `loop.py` provides provider-driven orchestration with checkpoint persistence.
5. `player_intent_provider.py` converts natural language into structured actions.
6. `enemy_llm_provider.py` performs bounded tactical decision-making.
7. `gradio_step.py` adapts engine steps into user-facing UI updates.

### 4.9 Screenshots of Working System
The repository supports two working interfaces:

1. A CLI play loop for deterministic testing and debugging.
2. A Gradio interface for browser-based interaction.

Screenshots can be captured directly from these two interfaces during final manuscript assembly. Since this repository version is source-focused, image assets for the documentation are not embedded in the current markdown file.

## 5 Testing and Evaluation
Testing in this project is strongly implementation-oriented. The automated suite covers the most failure-prone areas of the system: action validation, state routing, encounter logic, serialization, schema validation, LLM contract handling, and persistence.

The test organization indicates a deliberate incremental development process. Separate test files exist for pregame behavior, exploration, encounters, engine loop behavior, combat mechanics, entity regressions, schema validation, CLI persistence, telemetry, LLM bootstrap wiring, narration and conversation routing, and context-window management.

From an evaluation perspective, the project performs well in three important areas:

1. Rule enforcement: deterministic handlers prevent invalid actions from directly mutating state.
2. Observability: emitted events and checkpoints make runtime behavior inspectable.
3. Containment of LLM risk: model outputs are advisory and schema-constrained, not authoritative.

The main remaining evaluation challenges are qualitative rather than purely mechanical. These include the clarity of narration, the helpfulness of clarification responses, and the consistency of tactical enemy behavior under varied encounter conditions.

## 6 Results and Discussion
The implemented prototype demonstrates that a bounded-LLM architecture is viable for a turn-based dungeon crawler. The system successfully separates interpretation from execution. This is the most important technical result of the project.

The deterministic engine handles the parts that must remain correct: target legality, initiative, damage application, resistances, immunities, spell-slot consumption, room progression, encounter completion, and state transitions. The LLM improves usability and immersion by interpreting player language, generating contextual replies, and narrating event batches.

A notable strength of the project is that it remains functional even without live model access. Deterministic mode still supports gameplay, which is important for testing, debugging, and reproducibility. Another strength is the use of explicit event and checkpoint logs, which make the system easier to inspect than many monolithic AI-driven applications.

The main limitations are also clear. The project still depends on careful prompt design and context shaping to keep the LLM grounded. Narrative quality is not guaranteed, and tactical quality is bounded by the compact context provided to the model. In other words, the architecture is strong, but the language-facing experience still benefits from continued prompt and context refinement.

## 7 Ethical Considerations
This project raises several practical ethical considerations common to applied LLM systems.

First, the system must avoid presenting probabilistic output as unquestionable truth. The architecture addresses this by keeping the deterministic engine authoritative and by logging model interactions for inspection.

Second, user privacy must be considered if live API calls are enabled. Player text and state summaries may be sent to an external model provider. This means deployment should clearly disclose what is transmitted and should avoid sending unnecessary sensitive data.

Third, fairness and representational bias remain relevant even in a game setting. LLM-generated narration or dialogue may reflect biased phrasing if prompts and safeguards are not well controlled. Restricting the model to narrow domains and structured tasks helps reduce, but does not eliminate, this risk.

Finally, the project should be evaluated honestly as a prototype. It is a controlled research artifact, not a fully general autonomous game master.

## 8 Future Work
The repository already suggests several realistic next steps.

1. Expand content datasets to support more diverse dungeons, enemy archetypes, and spell interactions.
2. Improve context selection so the LLM sees richer but still bounded world information.
3. Add stronger evaluation for narrative quality and player satisfaction.
4. Introduce optional analytics dashboards over logs and telemetry.
5. Add multiplayer or multi-party orchestration support.
6. Explore a service-layer API if the engine is later deployed beyond local use.
7. Add visual assets and richer UI presentation without changing the deterministic core.

## 9 Conclusion
GameMasterAI shows that natural language interaction and deterministic game logic do not need to be competing design choices. By separating language interpretation from rule execution, the project creates a system that is both more flexible than a traditional text parser and more reliable than a free-form generative game master.

From a software engineering perspective, the project’s main contribution is architectural: it demonstrates a practical pattern for combining LLM subsystems with explicit schemas, event-driven orchestration, and deterministic state ownership. That pattern is broadly useful for interactive AI systems where correctness, traceability, and user-facing language all matter at the same time.