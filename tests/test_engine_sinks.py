import json

from game.engine.interfaces import EngineContext
from game.engine.sinks import InMemoryEventSink, SessionLogSink


def test_in_memory_event_sink_stores_batches_and_flattens():
    sink = InMemoryEventSink()
    ctx = EngineContext(session_id="sinks", step_count=3, seed=11)

    batch_1 = [{"type": "a"}, {"type": "b"}]
    batch_2 = [{"type": "c"}]

    sink.publish(batch_1, ctx)
    sink.publish(batch_2, ctx)

    assert len(sink.batches) == 2
    assert [event["type"] for event in sink.all_events()] == ["a", "b", "c"]

    batch_1[0]["type"] = "mutated"
    assert sink.batches[0][0]["type"] == "a"


def test_in_memory_event_sink_clear_resets_storage():
    sink = InMemoryEventSink()
    ctx = EngineContext(session_id="sinks")

    sink.publish([{"type": "a"}], ctx)
    sink.clear()

    assert sink.batches == []
    assert sink.all_events() == []


def test_session_log_sink_writes_jsonl_events(tmp_path):
    sink = SessionLogSink(base_dir=str(tmp_path / "sessions"))
    ctx = EngineContext(session_id="session_42", step_count=7, seed=99)
    events = [{"type": "turn_started", "actor_instance_id": "player_1"}]

    sink.publish(events, ctx)

    output_file = tmp_path / "sessions" / "session_42.jsonl"
    assert output_file.exists()

    lines = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["session_id"] == "session_42"
    assert record["step_count"] == 7
    assert record["turn_index"] == 7
    assert record["seed"] == 99
    assert record["event"] == events[0]
    assert isinstance(record["timestamp"], str)


def test_session_log_sink_appends_multiple_events_and_batches(tmp_path):
    sink = SessionLogSink(base_dir=str(tmp_path / "sessions"))
    ctx = EngineContext(session_id="session_99", step_count=1, seed=3)

    sink.publish([{"type": "a"}, {"type": "b"}], ctx)
    ctx.step_count = 2
    sink.publish([{"type": "c"}], ctx)

    output_file = tmp_path / "sessions" / "session_99.jsonl"
    lines = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3

    records = [json.loads(line) for line in lines]
    assert [record["event"]["type"] for record in records] == ["a", "b", "c"]
    assert [record["step_count"] for record in records] == [1, 1, 2]
    assert [record["turn_index"] for record in records] == [1, 1, 2]
