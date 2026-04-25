from __future__ import annotations

from datetime import datetime, timedelta

from stable_scheduler import DEFAULT_WINDOW_MS, Event, RecomputationBuffer

NOW = datetime(2026, 4, 24, 12, 0, 0)


class TestRecomputationBuffer:
    def test_empty_buffer_is_not_due(self):
        buf = RecomputationBuffer()
        assert buf.is_due(NOW) is False

    def test_first_event_is_due_immediately(self):
        buf = RecomputationBuffer()
        buf.push(Event(timestamp=NOW, kind="proposal"))
        assert buf.is_due(NOW) is True

    def test_not_due_inside_window(self):
        buf = RecomputationBuffer(window_ms=15 * 60 * 1000)
        buf.push(Event(timestamp=NOW, kind="proposal"))
        events = buf.flush(NOW)
        assert len(events) == 1
        buf.push(Event(timestamp=NOW + timedelta(minutes=5), kind="proposal"))
        assert buf.is_due(NOW + timedelta(minutes=5)) is False

    def test_due_at_window_boundary(self):
        buf = RecomputationBuffer(window_ms=15 * 60 * 1000)
        buf.push(Event(timestamp=NOW, kind="proposal"))
        buf.flush(NOW)
        buf.push(Event(timestamp=NOW + timedelta(minutes=10), kind="proposal"))
        assert buf.is_due(NOW + timedelta(minutes=15)) is True

    def test_flush_empties_buffer(self):
        buf = RecomputationBuffer()
        buf.push(Event(timestamp=NOW, kind="a"))
        buf.push(Event(timestamp=NOW, kind="b"))
        events = buf.flush(NOW)
        assert [e.kind for e in events] == ["a", "b"]
        assert buf.is_due(NOW) is False

    def test_next_flush_at_returns_now_before_first_flush(self):
        buf = RecomputationBuffer()
        assert buf.next_flush_at(NOW) == NOW

    def test_next_flush_at_advances_after_flush(self):
        buf = RecomputationBuffer(window_ms=15 * 60 * 1000)
        buf.push(Event(timestamp=NOW, kind="x"))
        buf.flush(NOW)
        assert buf.next_flush_at(NOW) == NOW + timedelta(minutes=15)

    def test_default_window_is_fifteen_minutes(self):
        assert DEFAULT_WINDOW_MS == 15 * 60 * 1000
