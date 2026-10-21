"""Per-session event bus (SPEC 5): append to events.jsonl, push to subscribers, catch up from any seq.

Single-threaded by design: emit() is called from the event loop (every API handler is async), so seq order,
the file and what subscribers see always agree.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pulselens.models import Event, EventType

Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self, path: Path, wall_ms: Callable[[], float] = lambda: time.time() * 1000) -> None:
        self.path = path
        self._wall_ms = wall_ms
        self.events: list[Event] = []
        if path.exists():  # a restarted server keeps serving catch-up for earlier sessions
            self.events = [
                Event.model_validate_json(line) for line in path.read_text("utf-8").splitlines() if line.strip()
            ]
        self._subscribers: list[Subscriber] = []

    def emit(self, type: EventType, payload: dict[str, Any], t_client: float | None = None) -> Event:
        event = Event(seq=len(self.events), t_server=self._wall_ms(), t_client=t_client, type=type, payload=payload)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump()) + "\n")
        self.events.append(event)
        for fn in list(self._subscribers):
            fn(event)
        return event

    def since(self, seq: int) -> list[Event]:
        """Events with seq >= `seq`: what a client that has seen everything before `seq` missed."""
        return self.events[max(0, seq) :]

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        self._subscribers.append(fn)
        return lambda: self._subscribers.remove(fn) if fn in self._subscribers else None
