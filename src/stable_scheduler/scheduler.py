from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum

from .authority import can_override
from .freeze import is_frozen, violates_hard_deadline
from .score import ScoreWeights, compute_score
from .threshold import DEFAULT_MOVE_THRESHOLD, dynamic_threshold, should_reschedule
from .types import Authority, Placement, Slot, Task, World


class Decision(Enum):
    APPLY = "apply"
    BLOCKED_BY_FREEZE = "blocked_by_freeze"
    BLOCKED_BY_THRESHOLD = "blocked_by_threshold"
    BLOCKED_BY_AUTHORITY = "blocked_by_authority"
    BLOCKED_BY_PIN = "blocked_by_pin"
    DEADLINE_OVERRIDE = "deadline_override"


@dataclass
class Proposal:
    task: Task
    proposed_slot: Slot
    authority: Authority


@dataclass
class Outcome:
    proposal: Proposal
    decision: Decision
    reason: str
    score_delta: float | None = None


@dataclass
class Scheduler:
    """Composes the stability primitives into a single decision pipeline.

    Pipeline:
        1. Pin check     (user pins are sacred)
        2. Authority     (can the proposer override the existing placement?)
        3. Freeze        (is the slot inside the freeze horizon?)
        4. Hard deadline (does it override the freeze?)
        5. Threshold     (is the improvement worth the churn?)

    Pass `on_outcome` to receive every decision (apply or reject) — this is
    the telemetry seam the README references. The callback runs synchronously
    inside `evaluate`; keep it cheap or push to a queue.
    """

    weights: ScoreWeights = field(default_factory=ScoreWeights)
    move_threshold: float = DEFAULT_MOVE_THRESHOLD
    freeze_hours: float = 2.0
    on_outcome: Callable[[Outcome], None] | None = None

    def evaluate(self, proposal: Proposal, world: World) -> Outcome:
        outcome = self._evaluate(proposal, world)
        if self.on_outcome is not None:
            self.on_outcome(outcome)
        return outcome

    def _evaluate(self, proposal: Proposal, world: World) -> Outcome:
        task = proposal.task
        existing = world.placements.get(task.id)
        proposed_slot = proposal.proposed_slot

        if task.pinned and proposal.authority != Authority.USER_PIN:
            return Outcome(proposal, Decision.BLOCKED_BY_PIN, "task is pinned by user")

        if existing and not can_override(proposal.authority, existing.authority):
            return Outcome(
                proposal,
                Decision.BLOCKED_BY_AUTHORITY,
                f"{proposal.authority.name} cannot override {existing.authority.name}",
            )

        bypasses_stability = proposal.authority in (
            Authority.USER_PIN,
            Authority.DEADLINE_OVERRIDE,
        )
        if bypasses_stability:
            return Outcome(proposal, Decision.APPLY, "high-authority bypass")

        current_slot = world.current_slot(task.id)
        if current_slot is not None and is_frozen(current_slot, world, self.freeze_hours):
            if violates_hard_deadline(task, current_slot):
                return Outcome(
                    proposal,
                    Decision.DEADLINE_OVERRIDE,
                    "frozen slot violates hard deadline; escalating",
                )
            return Outcome(
                proposal,
                Decision.BLOCKED_BY_FREEZE,
                f"current slot is within {self.freeze_hours}h freeze horizon",
            )

        threshold = dynamic_threshold(task, world.now, base=self.move_threshold)
        if not should_reschedule(task, proposed_slot, world, self.weights, threshold):
            current_score = (
                compute_score(task, current_slot, world, self.weights)
                if current_slot
                else 0.0
            )
            proposed_score = compute_score(task, proposed_slot, world, self.weights)
            return Outcome(
                proposal,
                Decision.BLOCKED_BY_THRESHOLD,
                f"improvement below {threshold:.2%} threshold",
                score_delta=proposed_score - current_score,
            )

        return Outcome(proposal, Decision.APPLY, "passes all stability checks")

    def apply(
        self, proposal: Proposal, world: World, now: datetime
    ) -> tuple[World, Task]:
        """Apply a proposal unconditionally. Use evaluate() first to gate.

        Returns the new `World` and the updated `Task`. The original `Task`
        is not mutated — `Task` is frozen, so `apply` returns a fresh copy
        with the move bookkeeping fields advanced.
        """
        task = proposal.task
        stale = task.last_move_date != now.date()
        new_count = (0 if stale else task.move_count_today) + 1
        new_task = replace(
            task,
            last_rescheduled_at=now,
            last_move_date=now.date(),
            move_count_today=new_count,
        )
        new_world = world.with_placement(
            Placement(
                task=new_task,
                slot=proposal.proposed_slot,
                authority=proposal.authority,
            )
        )
        return new_world, new_task
