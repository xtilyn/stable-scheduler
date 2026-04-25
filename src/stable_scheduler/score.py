from __future__ import annotations

from dataclasses import dataclass

from .types import Slot, Task, World


@dataclass
class ScoreWeights:
    """Tunable weights for the scoring function.

    `stability` is the parameter you will tune most. Start high (resist churn),
    relax based on user feedback. See the optimal-scheduling article for why.
    """

    deadline: float = 1.0
    priority: float = 1.0
    dependency: float = 1.0
    stability: float = 1.0


def deadline_pressure(task: Task, slot: Slot) -> float:
    hours_to_deadline = (task.deadline - slot.start).total_seconds() / 3600
    return max(0.0, 1.0 - hours_to_deadline / 24)


def priority_weight(task: Task) -> float:
    return task.priority / 10.0


def dependency_pressure(task: Task, world: World) -> float:
    return 1.0 if world.all_dependencies_complete(task) else 0.0


def reschedule_penalty(
    task: Task,
    proposed_slot: Slot,
    current_slot: Slot | None,
    world: World,
    weights: ScoreWeights,
) -> float:
    """Inverse-decay penalty: sharp for very recent moves, relaxes quickly.

    The first hour after placement is when trust forms. Inverse decay
    (1 / hours_since_last_move) creates the steep early penalty needed
    to resist churn during that window. See the optimal-scheduling article
    for why this shape over exponential decay.
    """
    if current_slot is None or current_slot == proposed_slot:
        return 0.0
    if task.last_rescheduled_at is None:
        return 0.0

    hours_since = (world.now - task.last_rescheduled_at).total_seconds() / 3600
    return weights.stability * (1.0 / max(hours_since, 0.1))


def compute_score(
    task: Task,
    proposed_slot: Slot,
    world: World,
    weights: ScoreWeights | None = None,
) -> float:
    """Total score for placing `task` in `proposed_slot` given current `world`.

    Higher is better. Includes the reschedule_penalty term that most
    schedulers leave out.
    """
    weights = weights or ScoreWeights()
    current_slot = world.current_slot(task.id)

    return (
        weights.deadline * deadline_pressure(task, proposed_slot)
        + weights.priority * priority_weight(task)
        + weights.dependency * dependency_pressure(task, world)
        - reschedule_penalty(task, proposed_slot, current_slot, world, weights)
    )
