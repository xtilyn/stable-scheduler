from __future__ import annotations

from datetime import datetime, timedelta

from stable_scheduler import (
    Authority,
    Placement,
    Proposal,
    Scheduler,
    ScoreWeights,
    Slot,
    Task,
    World,
)
from stable_scheduler.scheduler import Decision, Outcome

NOW = datetime(2026, 4, 24, 12, 0, 0)


def make_task(task_id: str = "t1", priority: int = 5, deadline_hours: float = 24, **kw) -> Task:
    return Task(
        id=task_id,
        priority=priority,
        deadline=NOW + timedelta(hours=deadline_hours),
        **kw,
    )


def make_slot(start_offset_hours: float = 1.0, duration_hours: float = 1.0) -> Slot:
    start = NOW + timedelta(hours=start_offset_hours)
    return Slot(start=start, end=start + timedelta(hours=duration_hours))


class TestDeadlineOverridePath:
    def test_frozen_slot_past_deadline_escalates(self):
        # Current slot is inside the freeze horizon AND ends after the deadline.
        # The scheduler must escalate via DEADLINE_OVERRIDE rather than block.
        task = make_task(deadline_hours=1.0)
        current_slot = Slot(
            start=NOW + timedelta(hours=0.5),
            end=NOW + timedelta(hours=1.5),
        )
        world = World(
            now=NOW,
            placements={
                task.id: Placement(task=task, slot=current_slot, authority=Authority.SERVER)
            },
        )
        scheduler = Scheduler(freeze_hours=2.0)
        proposal = Proposal(
            task=task,
            proposed_slot=make_slot(0.25, 0.5),
            authority=Authority.SERVER,
        )
        outcome = scheduler.evaluate(proposal, world)
        assert outcome.decision == Decision.DEADLINE_OVERRIDE

    def test_user_pin_bypass_applies(self):
        task = make_task()
        slot = make_slot(5.0)
        world = World(now=NOW)
        scheduler = Scheduler()
        proposal = Proposal(task=task, proposed_slot=slot, authority=Authority.USER_PIN)
        outcome = scheduler.evaluate(proposal, world)
        assert outcome.decision == Decision.APPLY
        assert "high-authority bypass" in outcome.reason


class TestApplyImmutability:
    def test_apply_returns_new_world_and_task(self):
        task = make_task()
        world = World(now=NOW)
        scheduler = Scheduler()
        proposal = Proposal(task=task, proposed_slot=make_slot(5.0), authority=Authority.SERVER)
        new_world, new_task = scheduler.apply(proposal, world, NOW)
        assert new_world is not world
        assert new_task is not task
        assert new_task.last_rescheduled_at == NOW
        assert new_task.move_count_today == 1

    def test_original_task_is_unchanged(self):
        task = make_task(move_count_today=3, last_move_date=NOW.date())
        world = World(now=NOW)
        scheduler = Scheduler()
        proposal = Proposal(task=task, proposed_slot=make_slot(5.0), authority=Authority.SERVER)
        scheduler.apply(proposal, world, NOW)
        assert task.move_count_today == 3
        assert task.last_rescheduled_at is None

    def test_new_world_contains_new_task_in_placement(self):
        task = make_task()
        world = World(now=NOW)
        scheduler = Scheduler()
        proposed = make_slot(5.0)
        proposal = Proposal(task=task, proposed_slot=proposed, authority=Authority.SERVER)
        new_world, new_task = scheduler.apply(proposal, world, NOW)
        placement = new_world.placements[task.id]
        assert placement.task is new_task
        assert placement.slot == proposed


class TestOnOutcomeHook:
    def test_callback_fires_on_apply(self):
        captured: list[Outcome] = []
        scheduler = Scheduler(on_outcome=captured.append)
        task = make_task()
        world = World(now=NOW)
        proposal = Proposal(task=task, proposed_slot=make_slot(5.0), authority=Authority.SERVER)
        outcome = scheduler.evaluate(proposal, world)
        assert len(captured) == 1
        assert captured[0] is outcome
        assert captured[0].decision == Decision.APPLY

    def test_callback_fires_on_reject(self):
        captured: list[Outcome] = []
        scheduler = Scheduler(on_outcome=captured.append)
        task = make_task(pinned=True)
        world = World(
            now=NOW,
            placements={
                task.id: Placement(task=task, slot=make_slot(), authority=Authority.USER_PIN)
            },
        )
        proposal = Proposal(task=task, proposed_slot=make_slot(5.0), authority=Authority.AGENT)
        scheduler.evaluate(proposal, world)
        assert len(captured) == 1
        assert captured[0].decision == Decision.BLOCKED_BY_PIN

    def test_no_callback_means_no_error(self):
        scheduler = Scheduler()
        task = make_task()
        world = World(now=NOW)
        proposal = Proposal(task=task, proposed_slot=make_slot(5.0), authority=Authority.SERVER)
        outcome = scheduler.evaluate(proposal, world)
        assert outcome.decision == Decision.APPLY


class TestScoreDelta:
    def test_threshold_rejection_populates_score_delta(self):
        weights = ScoreWeights(stability=0.0)
        task = make_task(
            deadline_hours=24,
            last_rescheduled_at=NOW - timedelta(hours=10),
        )
        current_slot = make_slot(5.0)
        proposed_slot = make_slot(5.5)
        world = World(
            now=NOW,
            placements={
                task.id: Placement(task=task, slot=current_slot, authority=Authority.SERVER)
            },
        )
        scheduler = Scheduler(weights=weights, move_threshold=0.50)
        proposal = Proposal(task=task, proposed_slot=proposed_slot, authority=Authority.SERVER)
        outcome = scheduler.evaluate(proposal, world)
        assert outcome.decision == Decision.BLOCKED_BY_THRESHOLD
        assert outcome.score_delta is not None
