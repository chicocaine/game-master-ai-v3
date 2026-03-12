from dataclasses import dataclass
import logging
from typing import List, Optional

from game.core.action import Action
from game.core.action_result import ActionResult
from game.enums import GameState
from game.engine.interfaces import ActionProvider, EngineContext, EventSink, Narrator, Persistence
from game.states.game_session import GameSession


logger = logging.getLogger(__name__)


@dataclass
class EngineLoopOutcome:
    session: GameSession
    steps: int
    stopped_reason: str
    last_action: Action | None = None
    last_result: ActionResult | None = None


def _resolve_next_action(
    session: GameSession,
    providers: List[ActionProvider],
    ctx: EngineContext,
) -> Optional[Action]:
    for provider in providers:
        try:
            action = provider.next_action(session, ctx)
        except Exception:
            # Provider failures are isolated so other providers can still operate.
            logger.exception(
                "Action provider failed; continuing with next provider.",
                extra={"provider": provider.__class__.__name__, "step_count": ctx.step_count},
            )
            continue
        if action is not None:
            return action
    return None


def _publish_events(
    events: List[dict],
    event_sinks: List[EventSink],
    ctx: EngineContext,
) -> None:
    if not events:
        return
    for sink in event_sinks:
        try:
            sink.publish(events, ctx)
        except Exception:
            # Sink failures are non-fatal; checkpoint persistence still runs.
            logger.exception(
                "Event sink publish failed; continuing.",
                extra={"sink": sink.__class__.__name__, "step_count": ctx.step_count},
            )
            continue


def run_engine_loop(
    session: GameSession,
    providers: List[ActionProvider],
    event_sinks: List[EventSink],
    narrator: Narrator | None,
    persistence: Persistence,
    ctx: EngineContext,
    max_steps: int = 10000,
) -> EngineLoopOutcome:
    steps = 0
    action: Action | None = None
    result: ActionResult | None = None
    while steps < max_steps:
        action = _resolve_next_action(session, providers, ctx)
        if action is None:
            return EngineLoopOutcome(session=session, steps=steps, stopped_reason="idle")

        result = session.handle_action(action)

        _publish_events(result.events, event_sinks, ctx)

        if narrator is not None and result.events:
            try:
                narrator.narrate(result.events, session, ctx)
            except Exception:
                logger.exception(
                    "Narrator failed; continuing without narration.",
                    extra={"step_count": ctx.step_count},
                )

        try:
            persistence.save_checkpoint(session, action, result, ctx)
        except Exception:
            # Retry once. If this still fails, terminate loop with failure reason.
            logger.exception(
                "Checkpoint save failed; retrying once.",
                extra={"step_count": ctx.step_count, "session_id": ctx.session_id},
            )
            try:
                persistence.save_checkpoint(session, action, result, ctx)
            except Exception:
                logger.exception(
                    "Checkpoint retry failed; terminating engine loop.",
                    extra={"step_count": ctx.step_count, "session_id": ctx.session_id},
                )
                return EngineLoopOutcome(
                    session=session,
                    steps=steps,
                    stopped_reason="persistence_failure",
                    last_action=action,
                    last_result=result,
                )

        steps += 1
        ctx.step_count += 1

        if session.state is GameState.POSTGAME:
            return EngineLoopOutcome(
                session=session,
                steps=steps,
                stopped_reason="postgame",
                last_action=action,
                last_result=result,
            )

    return EngineLoopOutcome(
        session=session,
        steps=steps,
        stopped_reason="max_steps",
        last_action=action,
        last_result=result,
    )
