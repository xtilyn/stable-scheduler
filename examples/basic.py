"""End-to-end demo: an agent tries to churn a task; the scheduler resists.

Run from the project root:
    python examples/basic.py
"""

from datetime import datetime, timedelta

from stable_scheduler import (
    Authority,
    Placement,
    Proposal,
    Scheduler,
    Slot,
    Task,
    World,
)


def main() -> None:
    now = datetime(2026, 4, 24, 12, 0, 0)

    task = Task(
        id="ship-stable-scheduler",
        priority=8,
        deadline=now + timedelta(hours=72),
        last_rescheduled_at=now - timedelta(minutes=10),
    )

    initial_slot = Slot(start=now + timedelta(hours=6), end=now + timedelta(hours=8))
    world = World(
        now=now,
        placements={
            task.id: Placement(task=task, slot=initial_slot, authority=Authority.SERVER)
        },
    )

    scheduler = Scheduler(freeze_hours=2.0, move_threshold=0.15)

    proposed_slot = Slot(start=now + timedelta(hours=5), end=now + timedelta(hours=7))
    agent_proposal = Proposal(task=task, proposed_slot=proposed_slot, authority=Authority.AGENT)
    outcome = scheduler.evaluate(agent_proposal, world)
    print(f"Agent proposes minor improvement -> {outcome.decision.value}: {outcome.reason}")

    user_proposal = Proposal(
        task=task,
        proposed_slot=Slot(start=now + timedelta(hours=24), end=now + timedelta(hours=26)),
        authority=Authority.USER_PIN,
    )
    outcome = scheduler.evaluate(user_proposal, world)
    print(f"User pins later slot       -> {outcome.decision.value}: {outcome.reason}")

    near_term_slot = Slot(start=now + timedelta(hours=1), end=now + timedelta(hours=2))
    world_near = World(
        now=now,
        placements={
            task.id: Placement(task=task, slot=near_term_slot, authority=Authority.SERVER)
        },
    )
    proposal = Proposal(
        task=task,
        proposed_slot=Slot(start=now + timedelta(hours=10), end=now + timedelta(hours=12)),
        authority=Authority.SERVER,
    )
    outcome = scheduler.evaluate(proposal, world_near)
    print(f"Server tries to move frozen task -> {outcome.decision.value}: {outcome.reason}")


if __name__ == "__main__":
    main()
