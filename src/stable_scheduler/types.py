from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum


class Authority(IntEnum):
    """Who initiated a schedule change. Higher value wins on conflict."""

    OFFLINE_CLIENT = 1
    AGENT = 2
    SERVER = 3
    DEADLINE_OVERRIDE = 4
    USER_PIN = 5


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime

    def __lt__(self, other: Slot) -> bool:
        return self.start < other.start


@dataclass(frozen=True)
class Task:
    id: str
    priority: int
    deadline: datetime
    dependencies: tuple[str, ...] = ()
    last_rescheduled_at: datetime | None = None
    pinned: bool = False
    move_count_today: int = 0
    last_move_date: date | None = None

    def moves_today(self, now: datetime) -> int:
        """Move count anchored to `now.date()`. Returns 0 if the stored
        count is stale (i.e. last move happened on a previous day)."""
        if self.last_move_date != now.date():
            return 0
        return self.move_count_today


@dataclass
class Placement:
    task: Task
    slot: Slot
    authority: Authority


@dataclass
class World:
    """Snapshot of the scheduler's view at a point in time."""

    now: datetime
    placements: dict[str, Placement] = field(default_factory=dict)
    completed_dependencies: set[str] = field(default_factory=set)

    def current_slot(self, task_id: str) -> Slot | None:
        placement = self.placements.get(task_id)
        return placement.slot if placement else None

    def all_dependencies_complete(self, task: Task) -> bool:
        return all(dep in self.completed_dependencies for dep in task.dependencies)

    def with_placement(self, placement: Placement) -> World:
        new_placements = dict(self.placements)
        new_placements[placement.task.id] = placement
        return World(
            now=self.now,
            placements=new_placements,
            completed_dependencies=set(self.completed_dependencies),
        )


def iter_placements(world: World) -> Iterable[Placement]:
    return world.placements.values()
