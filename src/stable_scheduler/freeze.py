from __future__ import annotations

from datetime import timedelta

from .types import Slot, Task, World

DEFAULT_FREEZE_HOURS = 2.0


def is_frozen(
    slot: Slot,
    world: World,
    freeze_hours: float = DEFAULT_FREEZE_HOURS,
) -> bool:
    """Tasks within the freeze horizon cannot be moved.

    The user's immediate schedule is guaranteed stable. They can look at
    the next N hours and know it will not change. Beyond N hours the
    scheduler can optimize freely (subject to penalty + threshold).
    """
    horizon = world.now + timedelta(hours=freeze_hours)
    return slot.start <= horizon


def violates_hard_deadline(task: Task, slot: Slot) -> bool:
    """The one exception that overrides the freeze horizon.

    A frozen task that will miss its deadline must move and be flagged
    explicitly. Treat as escalation, not normal recomputation.
    """
    return slot.end > task.deadline
