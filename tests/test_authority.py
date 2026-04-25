from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from stable_scheduler import Authority, Placement, Slot, Task, can_override, resolve_conflict

NOW = datetime(2026, 4, 24, 12, 0, 0)


def make_task(task_id: str = "t1") -> Task:
    return Task(id=task_id, priority=5, deadline=NOW + timedelta(hours=24))


def make_placement(task_id: str, authority: Authority) -> Placement:
    slot = Slot(start=NOW + timedelta(hours=1), end=NOW + timedelta(hours=2))
    return Placement(task=make_task(task_id), slot=slot, authority=authority)


class TestCanOverride:
    def test_higher_authority_overrides_lower(self):
        assert can_override(Authority.SERVER, Authority.AGENT) is True

    def test_lower_authority_cannot_override_higher(self):
        assert can_override(Authority.AGENT, Authority.SERVER) is False

    def test_user_pin_beats_everything(self):
        assert can_override(Authority.USER_PIN, Authority.DEADLINE_OVERRIDE) is True
        assert can_override(Authority.USER_PIN, Authority.SERVER) is True

    def test_same_tier_can_replace_itself(self):
        assert can_override(Authority.SERVER, Authority.SERVER) is True

    def test_offline_client_is_lowest(self):
        assert can_override(Authority.OFFLINE_CLIENT, Authority.AGENT) is False
        assert can_override(Authority.AGENT, Authority.OFFLINE_CLIENT) is True


class TestResolveConflict:
    def test_higher_authority_wins(self):
        a = make_placement("t1", Authority.AGENT)
        b = make_placement("t1", Authority.SERVER)
        assert resolve_conflict(a, b) is b

    def test_existing_kept_when_challenger_lower(self):
        a = make_placement("t1", Authority.SERVER)
        b = make_placement("t1", Authority.AGENT)
        assert resolve_conflict(a, b) is a

    def test_same_tier_challenger_wins(self):
        a = make_placement("t1", Authority.SERVER)
        b = make_placement("t1", Authority.SERVER)
        assert resolve_conflict(a, b) is b

    def test_cross_task_conflict_raises(self):
        a = make_placement("t1", Authority.SERVER)
        b = make_placement("t2", Authority.SERVER)
        with pytest.raises(ValueError):
            resolve_conflict(a, b)
