from dataclasses import dataclass, field
from typing import Any, Dict, List

from game.engine.interfaces import EngineContext, EventSink


@dataclass
class InMemoryEventSink(EventSink):
    batches: List[List[Dict[str, Any]]] = field(default_factory=list)

    def publish(self, events: List[Dict[str, Any]], ctx: EngineContext) -> None:
        # Store a snapshot of each batch to avoid caller-side mutations leaking in.
        self.batches.append([dict(event) for event in events])

    def all_events(self) -> List[Dict[str, Any]]:
        flattened: List[Dict[str, Any]] = []
        for batch in self.batches:
            flattened.extend(batch)
        return flattened

    def clear(self) -> None:
        self.batches.clear()
