"""stable-scheduler: a scheduling library that optimizes for stability, not just optimality.

Reference: https://arjona.dev/writing/optimal-scheduling
"""

from .authority import can_override, resolve_conflict
from .buffer import DEFAULT_WINDOW_MS, Event, RecomputationBuffer
from .freeze import DEFAULT_FREEZE_HOURS, is_frozen, violates_hard_deadline
from .scheduler import Decision, Outcome, Proposal, Scheduler
from .score import (
    ScoreWeights,
    compute_score,
    deadline_pressure,
    dependency_pressure,
    priority_weight,
    reschedule_penalty,
)
from .threshold import (
    DEFAULT_MOVE_THRESHOLD,
    dynamic_threshold,
    relative_improvement,
    should_reschedule,
)
from .types import Authority, Placement, Slot, Task, World

__version__ = "0.1.0"

__all__ = [
    "Authority",
    "Decision",
    "DEFAULT_FREEZE_HOURS",
    "DEFAULT_MOVE_THRESHOLD",
    "DEFAULT_WINDOW_MS",
    "Event",
    "Outcome",
    "Placement",
    "Proposal",
    "RecomputationBuffer",
    "Scheduler",
    "ScoreWeights",
    "Slot",
    "Task",
    "World",
    "can_override",
    "compute_score",
    "deadline_pressure",
    "dependency_pressure",
    "dynamic_threshold",
    "is_frozen",
    "priority_weight",
    "relative_improvement",
    "reschedule_penalty",
    "resolve_conflict",
    "should_reschedule",
    "violates_hard_deadline",
    "__version__",
]
