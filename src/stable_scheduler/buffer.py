from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

DEFAULT_WINDOW_MS = 15 * 60 * 1000


@dataclass
class Event:
    timestamp: datetime
    kind: str
    payload: Any = None


@dataclass
class RecomputationBuffer:
    """Batch events into windows so the schedule changes at most once per window.

    The point is not to reduce compute cost (recomputation is cheap). It is
    to reduce cognitive cost. A schedule that updates every 15 minutes is one
    the user can check, internalize, and act on before it changes again.
    """

    window_ms: int = DEFAULT_WINDOW_MS
    _events: deque[Event] = field(default_factory=deque)
    _last_flush: datetime | None = None

    def push(self, event: Event) -> None:
        self._events.append(event)

    def is_due(self, now: datetime) -> bool:
        if self._last_flush is None:
            return bool(self._events)
        elapsed = (now - self._last_flush).total_seconds() * 1000
        return elapsed >= self.window_ms and bool(self._events)

    def flush(self, now: datetime) -> list[Event]:
        events = list(self._events)
        self._events.clear()
        self._last_flush = now
        return events

    def next_flush_at(self, now: datetime) -> datetime:
        if self._last_flush is None:
            return now
        return self._last_flush + timedelta(milliseconds=self.window_ms)
