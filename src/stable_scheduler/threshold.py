from __future__ import annotations

from datetime import datetime

from .score import ScoreWeights, compute_score
from .types import Slot, Task, World

DEFAULT_MOVE_THRESHOLD = 0.15


def relative_improvement(current: float, proposed: float) -> float:
    if current == 0:
        return float("inf") if proposed > 0 else 0.0
    return (proposed - current) / abs(current)


def should_reschedule(
    task: Task,
    proposed_slot: Slot,
    world: World,
    weights: ScoreWeights | None = None,
    threshold: float = DEFAULT_MOVE_THRESHOLD,
) -> bool:
    """Only move if the new slot is meaningfully better, not just marginally.

    A 4% improvement is rarely worth the user-visible churn. The default 15%
    threshold filters out moves that look correct to the optimizer but feel
    like noise to the user.
    """
    current_slot = world.current_slot(task.id)
    if current_slot is None:
        return True

    current_score = compute_score(task, current_slot, world, weights)
    proposed_score = compute_score(task, proposed_slot, world, weights)

    return relative_improvement(current_score, proposed_score) > threshold


def dynamic_threshold(
    task: Task, now: datetime, base: float = DEFAULT_MOVE_THRESHOLD
) -> float:
    """Tasks that have already moved today get a higher threshold.

    Natural damping: the more a task has churned, the harder it is to move again.
    `now` anchors "today" so a stale count from a prior day does not bias the
    threshold.
    """
    return base * (1 + 0.5 * task.moves_today(now))
