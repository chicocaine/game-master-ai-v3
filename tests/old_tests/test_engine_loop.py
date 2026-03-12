from game.core.action import create_action
from game.core.action_result import ActionResult
from game.core.enums import ActionType
from game.engine.interfaces import EngineContext
from game.engine.loop import run_engine_loop
from game.engine.providers import QueueActionProvider, TurnAwareEnemyStubProvider
from game.enums import GameState


class _StubSession:
    def __init__(self) -> None:
        self.state = GameState.PREGAME
        self.handled_action_ids: list[str] = []

    def handle_action(self, action):
        self.handled_action_ids.append(action.action_id)
        if action.type is ActionType.FINISH:
            self.state = GameState.POSTGAME
            return ActionResult.success(events=[{"type": "game_finished"}])
        return ActionResult.success(events=[{"type": "action_handled", "action_id": action.action_id}])


class _EncounterTurnSession:
    def __init__(self) -> None:
        self.state = GameState.ENCOUNTER
        self.handled_actions: list[tuple[ActionType, str]] = []
        self.encounter = type("EncounterStateStub", (), {})()
        self.encounter.turn_order = ["player_1", "enemy_1"]
        self.encounter.current_turn_index = 0

    def _current_actor(self) -> str:
        return self.encounter.turn_order[self.encounter.current_turn_index]

    def handle_action(self, action):
        self.handled_actions.append((action.type, action.actor_instance_id))

        if action.type is ActionType.END_TURN:
            # Deterministic turn handoff for integration testing.
            self.encounter.current_turn_index = (self.encounter.current_turn_index + 1) % len(self.encounter.turn_order)

        return ActionResult.success(
            events=[
                {
                    "type": "action_handled",
                    "action_type": action.type.value,
                    "actor_instance_id": action.actor_instance_id,
                    "next_actor_instance_id": self._current_actor(),
                }
            ]
        )


class _CollectingSink:
    def __init__(self) -> None:
        self.batches: list[list[dict]] = []

    def publish(self, events, ctx):
        self.batches.append(list(events))


class _FailingSink:
    def publish(self, events, ctx):
        raise RuntimeError("sink unavailable")


class _CollectingNarrator:
    def __init__(self) -> None:
        self.calls = 0

    def narrate(self, events, session, ctx):
        self.calls += 1
        return "ok"


class _FailingNarrator:
    def narrate(self, events, session, ctx):
        raise RuntimeError("narrator failure")


class _PersistenceRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def load(self, session_id):
        return None

    def save_checkpoint(self, session, action, result, ctx):
        self.calls += 1


class _FailOncePersistence:
    def __init__(self) -> None:
        self.calls = 0

    def load(self, session_id):
        return None

    def save_checkpoint(self, session, action, result, ctx):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient failure")


class _FailTwicePersistence:
    def __init__(self) -> None:
        self.calls = 0

    def load(self, session_id):
        return None

    def save_checkpoint(self, session, action, result, ctx):
        self.calls += 1
        raise RuntimeError("hard failure")


def test_queue_action_provider_dequeues_in_order():
    action_1 = create_action(ActionType.CONVERSE, {"message": "hello"}, actor_instance_id="player_1")
    action_2 = create_action(ActionType.END_TURN, {}, actor_instance_id="player_1")
    provider = QueueActionProvider([action_1, action_2])
    ctx = EngineContext(session_id="s1")
    session = _StubSession()

    assert provider.next_action(session, ctx) is action_1
    assert provider.next_action(session, ctx) is action_2
    assert provider.next_action(session, ctx) is None
    assert provider.pending_count() == 0


def test_engine_loop_uses_first_provider_with_available_action():
    action_1 = create_action(ActionType.CONVERSE, {"message": "first"}, actor_instance_id="player_1")
    action_2 = create_action(ActionType.CONVERSE, {"message": "second"}, actor_instance_id="player_1")
    providers = [QueueActionProvider([action_1]), QueueActionProvider([action_2])]
    session = _StubSession()
    sink = _CollectingSink()
    narrator = _CollectingNarrator()
    persistence = _PersistenceRecorder()
    ctx = EngineContext(session_id="s2")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[sink],
        narrator=narrator,
        persistence=persistence,
        ctx=ctx,
        max_steps=1,
    )

    assert outcome.stopped_reason == "max_steps"
    assert outcome.steps == 1
    assert session.handled_action_ids == [action_1.action_id]
    assert len(sink.batches) == 1
    assert narrator.calls == 1
    assert persistence.calls == 1
    assert ctx.step_count == 1


def test_engine_loop_continues_when_sink_fails():
    action = create_action(ActionType.CONVERSE, {"message": "ping"}, actor_instance_id="player_1")
    providers = [QueueActionProvider([action])]
    session = _StubSession()
    healthy_sink = _CollectingSink()
    persistence = _PersistenceRecorder()
    ctx = EngineContext(session_id="s3")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[_FailingSink(), healthy_sink],
        narrator=_FailingNarrator(),
        persistence=persistence,
        ctx=ctx,
        max_steps=1,
    )

    assert outcome.stopped_reason == "max_steps"
    assert outcome.steps == 1
    assert len(healthy_sink.batches) == 1
    assert persistence.calls == 1


def test_engine_loop_retries_persistence_once_then_succeeds():
    action = create_action(ActionType.CONVERSE, {"message": "persist"}, actor_instance_id="player_1")
    providers = [QueueActionProvider([action])]
    session = _StubSession()
    persistence = _FailOncePersistence()
    ctx = EngineContext(session_id="s4")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[],
        narrator=None,
        persistence=persistence,
        ctx=ctx,
        max_steps=1,
    )

    assert outcome.stopped_reason == "max_steps"
    assert outcome.steps == 1
    assert persistence.calls == 2


def test_engine_loop_stops_when_persistence_fails_twice():
    action = create_action(ActionType.CONVERSE, {"message": "persist"}, actor_instance_id="player_1")
    providers = [QueueActionProvider([action])]
    session = _StubSession()
    persistence = _FailTwicePersistence()
    ctx = EngineContext(session_id="s5")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[],
        narrator=None,
        persistence=persistence,
        ctx=ctx,
        max_steps=5,
    )

    assert outcome.stopped_reason == "persistence_failure"
    assert outcome.steps == 0
    assert persistence.calls == 2


def test_engine_loop_stops_on_postgame_state():
    action = create_action(ActionType.FINISH, {}, actor_instance_id="system")
    providers = [QueueActionProvider([action])]
    session = _StubSession()
    persistence = _PersistenceRecorder()
    ctx = EngineContext(session_id="s6")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[],
        narrator=None,
        persistence=persistence,
        ctx=ctx,
        max_steps=10,
    )

    assert outcome.stopped_reason == "postgame"
    assert outcome.steps == 1
    assert session.state is GameState.POSTGAME


def test_engine_loop_stops_idle_when_no_provider_has_action():
    session = _StubSession()
    persistence = _PersistenceRecorder()
    ctx = EngineContext(session_id="s7")

    outcome = run_engine_loop(
        session=session,
        providers=[QueueActionProvider([])],
        event_sinks=[],
        narrator=None,
        persistence=persistence,
        ctx=ctx,
        max_steps=5,
    )

    assert outcome.stopped_reason == "idle"
    assert outcome.steps == 0
    assert persistence.calls == 0
    assert ctx.step_count == 0


def test_engine_loop_returns_clean_outcome_for_zero_max_steps():
    action = create_action(ActionType.CONVERSE, {"message": "noop"}, actor_instance_id="player_1")
    providers = [QueueActionProvider([action])]
    session = _StubSession()
    persistence = _PersistenceRecorder()
    ctx = EngineContext(session_id="s10")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[],
        narrator=None,
        persistence=persistence,
        ctx=ctx,
        max_steps=0,
    )

    assert outcome.stopped_reason == "max_steps"
    assert outcome.steps == 0
    assert outcome.last_action is None
    assert outcome.last_result is None


def test_engine_loop_handoff_player_then_enemy_stub_provider():
    player_end_turn = create_action(ActionType.END_TURN, {}, actor_instance_id="player_1")
    providers = [QueueActionProvider([player_end_turn]), TurnAwareEnemyStubProvider()]
    session = _EncounterTurnSession()
    persistence = _PersistenceRecorder()
    ctx = EngineContext(session_id="s8")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[],
        narrator=None,
        persistence=persistence,
        ctx=ctx,
        max_steps=2,
    )

    assert outcome.stopped_reason == "max_steps"
    assert outcome.steps == 2
    assert session.handled_actions == [
        (ActionType.END_TURN, "player_1"),
        (ActionType.END_TURN, "enemy_1"),
    ]
    assert persistence.calls == 2
    assert ctx.step_count == 2


def test_engine_loop_uses_enemy_stub_when_primary_provider_empty_on_enemy_turn():
    session = _EncounterTurnSession()
    session.encounter.current_turn_index = 1
    providers = [QueueActionProvider([]), TurnAwareEnemyStubProvider()]
    persistence = _PersistenceRecorder()
    ctx = EngineContext(session_id="s9")

    outcome = run_engine_loop(
        session=session,
        providers=providers,
        event_sinks=[],
        narrator=None,
        persistence=persistence,
        ctx=ctx,
        max_steps=1,
    )

    assert outcome.stopped_reason == "max_steps"
    assert outcome.steps == 1
    assert session.handled_actions == [(ActionType.END_TURN, "enemy_1")]
