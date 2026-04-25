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
    compute_score,
    dynamic_threshold,
    is_frozen,
    reschedule_penalty,
    should_reschedule,
)
from stable_scheduler.scheduler import Decision

NOW = datetime(2026, 4, 24, 12, 0, 0)


def make_task(task_id: str = "t1", priority: int = 5, deadline_hours: int = 24, **kw) -> Task:
    return Task(
        id=task_id,
        priority=priority,
        deadline=NOW + timedelta(hours=deadline_hours),
        **kw,
    )


def make_slot(start_offset_hours: float = 1.0, duration_hours: float = 1.0) -> Slot:
    start = NOW + timedelta(hours=start_offset_hours)
    return Slot(start=start, end=start + timedelta(hours=duration_hours))


def make_world(now: datetime = NOW, **kw) -> World:
    return World(now=now, **kw)


class TestReschedulePenalty:
    def test_no_penalty_for_first_placement(self):
        task = make_task()
        slot = make_slot()
        world = make_world()
        assert reschedule_penalty(task, slot, None, world, ScoreWeights()) == 0.0

    def test_no_penalty_when_slot_unchanged(self):
        task = make_task()
        slot = make_slot()
        world = make_world()
        assert reschedule_penalty(task, slot, slot, world, ScoreWeights()) == 0.0

    def test_high_penalty_for_recent_move(self):
        task = make_task(last_rescheduled_at=NOW - timedelta(minutes=6))
        old_slot = make_slot(1.0)
        new_slot = make_slot(3.0)
        world = make_world()
        penalty = reschedule_penalty(task, new_slot, old_slot, world, ScoreWeights(stability=1.0))
        assert penalty > 5.0

    def test_low_penalty_for_old_placement(self):
        task = make_task(last_rescheduled_at=NOW - timedelta(hours=10))
        old_slot = make_slot(1.0)
        new_slot = make_slot(3.0)
        world = make_world()
        penalty = reschedule_penalty(task, new_slot, old_slot, world, ScoreWeights(stability=1.0))
        assert penalty < 0.2


class TestShouldReschedule:
    def test_first_placement_always_proceeds(self):
        task = make_task()
        slot = make_slot()
        world = make_world()
        assert should_reschedule(task, slot, world) is True

    def test_marginal_improvement_blocked(self):
        task = make_task(last_rescheduled_at=NOW - timedelta(hours=8))
        current_slot = make_slot(5.0)
        proposed_slot = make_slot(5.5)
        world = make_world(
            placements={
                task.id: Placement(task=task, slot=current_slot, authority=Authority.SERVER)
            }
        )
        assert should_reschedule(task, proposed_slot, world, threshold=0.50) is False

    def test_substantial_improvement_proceeds(self):
        weights = ScoreWeights(stability=0)
        task = make_task(deadline_hours=24, last_rescheduled_at=NOW - timedelta(hours=10))
        current_slot = make_slot(0.5)
        proposed_slot = make_slot(22.0)
        world = make_world(
            placements={
                task.id: Placement(task=task, slot=current_slot, authority=Authority.SERVER)
            }
        )
        result = should_reschedule(task, proposed_slot, world, weights=weights, threshold=0.10)
        assert result is True


class TestSchedulerPipeline:
    def test_pin_blocks_non_user_authority(self):
        task = make_task(pinned=True)
        slot = make_slot()
        world = make_world(
            placements={task.id: Placement(task=task, slot=slot, authority=Authority.USER_PIN)}
        )
        scheduler = Scheduler()
        proposal = Proposal(task=task, proposed_slot=make_slot(5.0), authority=Authority.AGENT)
        outcome = scheduler.evaluate(proposal, world)
        assert outcome.decision == Decision.BLOCKED_BY_PIN

    def test_freeze_horizon_blocks_near_term_moves(self):
        task = make_task(last_rescheduled_at=NOW - timedelta(hours=8))
        current_slot = make_slot(0.5)
        proposed_slot = make_slot(10.0)
        world = make_world(
            placements={
                task.id: Placement(task=task, slot=current_slot, authority=Authority.SERVER)
            }
        )
        scheduler = Scheduler(freeze_hours=2.0)
        proposal = Proposal(task=task, proposed_slot=proposed_slot, authority=Authority.SERVER)
        outcome = scheduler.evaluate(proposal, world)
        assert outcome.decision == Decision.BLOCKED_BY_FREEZE

    def test_low_authority_cannot_override_high_authority(self):
        task = make_task()
        slot = make_slot(5.0)
        world = make_world(
            placements={
                task.id: Placement(task=task, slot=slot, authority=Authority.SERVER)
            }
        )
        scheduler = Scheduler()
        proposal = Proposal(
            task=task, proposed_slot=make_slot(8.0), authority=Authority.AGENT
        )
        outcome = scheduler.evaluate(proposal, world)
        assert outcome.decision == Decision.BLOCKED_BY_AUTHORITY


class TestComputeScore:
    def test_dependency_complete_increases_score(self):
        task = make_task(dependencies=("dep1",))
        slot = make_slot(5.0)
        world_blocked = make_world()
        world_ready = make_world(completed_dependencies={"dep1"})
        assert compute_score(task, slot, world_ready) > compute_score(task, slot, world_blocked)

    def test_tighter_deadline_increases_score(self):
        urgent = make_task(deadline_hours=2)
        relaxed = make_task(deadline_hours=48)
        slot = make_slot(1.0)
        world = make_world()
        assert compute_score(urgent, slot, world) > compute_score(relaxed, slot, world)


class TestDailyMoveCounter:
    def test_apply_resets_count_on_new_day(self):
        task = make_task(
            move_count_today=4,
            last_move_date=(NOW - timedelta(days=1)).date(),
            last_rescheduled_at=NOW - timedelta(days=1),
        )
        far_slot = make_slot(start_offset_hours=10.0)
        current = Placement(task=task, slot=make_slot(8.0), authority=Authority.SERVER)
        world = make_world(placements={task.id: current})
        scheduler = Scheduler()
        proposal = Proposal(task=task, proposed_slot=far_slot, authority=Authority.SERVER)
        _, updated = scheduler.apply(proposal, world, NOW)
        assert updated.last_move_date == NOW.date()
        assert updated.move_count_today == 1
        assert task.move_count_today == 4

    def test_dynamic_threshold_ignores_stale_count(self):
        task = make_task(
            move_count_today=10,
            last_move_date=(NOW - timedelta(days=2)).date(),
        )
        assert dynamic_threshold(task, NOW, base=0.15) == 0.15

    def test_dynamic_threshold_uses_today_count(self):
        task = make_task(move_count_today=2, last_move_date=NOW.date())
        assert dynamic_threshold(task, NOW, base=0.15) == 0.15 * 2.0


class TestFreezeHorizon:
    def test_slot_inside_horizon_is_frozen(self):
        slot = make_slot(0.5)
        world = make_world()
        assert is_frozen(slot, world, freeze_hours=2.0) is True

    def test_slot_outside_horizon_is_not_frozen(self):
        slot = make_slot(5.0)
        world = make_world()
        assert is_frozen(slot, world, freeze_hours=2.0) is False
