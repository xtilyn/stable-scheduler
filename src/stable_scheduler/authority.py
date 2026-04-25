from __future__ import annotations

from .types import Authority, Placement


def can_override(new: Authority, existing: Authority) -> bool:
    """Higher-or-equal authority can overwrite. Lower cannot.

    Hierarchy (high to low):
        USER_PIN > DEADLINE_OVERRIDE > SERVER > AGENT > OFFLINE_CLIENT

    A user pin always wins. An agent suggestion cannot override a server
    decision. The server can replace its own previous decision (same tier).
    """
    return new.value >= existing.value


def resolve_conflict(a: Placement, b: Placement) -> Placement:
    """Pick the winner when two placements target the same task."""
    if a.task.id != b.task.id:
        raise ValueError("resolve_conflict called on placements for different tasks")

    if can_override(b.authority, a.authority):
        return b
    return a
