"""Pareto curves across workloads: how does the churn/quality trade-off
shape change as the proposal distribution changes?

Same harness, same quality metric, same threshold sweep, varied across
three proposal distributions:

    quiet       sparse proposals, all small toward-deadline shifts.
                Models a settled-state schedule where the optimizer
                rarely fires.
    chaotic     dense proposals, mixed magnitudes (50% small marginal,
                50% large corrective). Models a busy planning system
                where the optimizer is constantly recomputing.
    adversarial dense proposals, all small (sub-threshold by design).
                Models the failure mode where many tiny nudges drift
                the schedule under the user without any individual
                update being big enough to gate.

Each curve is one workload. Each point on a curve is one threshold
value, mean ± stddev across 50 seeds. The library default (0.15) is
ringed on every curve so you can read the trade-off slope at the same
x-coordinate per workload.

Quality metric: mean absolute deviation of `slot.end` from a reference
"ideal end" of `deadline - 0.5h`. Lower is better. Independent of the
scheduler's own scoring function so the metric is not coupled to the
gate.

Run:
    pip install -e ".[examples]"
    python examples/sim_pareto_workloads.py
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt

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
from stable_scheduler.scheduler import Decision


N_TASKS = 60
TICK_MINUTES = 5
SIM_HOURS = 24
SEEDS = list(range(50))
THRESHOLDS = [0.0, 0.05, 0.10, 0.15, 0.25, 0.50, 1.0]
DEFAULT_THRESHOLD = 0.15
IDEAL_END_BUFFER_HOURS = 0.5
START = datetime(2026, 4, 24, 0, 0, 0)


Proposer = Callable[[Task, World, random.Random], Proposal]


@dataclass(frozen=True)
class Workload:
    name: str
    proposer: Proposer
    proposal_rate: float
    color: str


def make_tasks(rng: random.Random) -> list[Task]:
    """Deadlines tight enough that `deadline_pressure` is in its meaningful
    range (clamped to 0 for slots > 24h before deadline)."""
    tasks = []
    for i in range(N_TASKS):
        deadline_hours = rng.uniform(10.0, 22.0)
        tasks.append(
            Task(
                id=f"t{i:03d}",
                priority=rng.randint(1, 10),
                deadline=START + timedelta(hours=deadline_hours),
            )
        )
    return tasks


def initial_world(tasks: list[Task], rng: random.Random) -> World:
    """Place each task a few hours into the day, well before its deadline.
    Avoids the freeze horizon at sim start; leaves headroom for shifts."""
    placements: dict[str, Placement] = {}
    for task in tasks:
        deadline_hours = (task.deadline - START).total_seconds() / 3600
        upper = max(3.5, deadline_hours - 4.0)
        start_hours = rng.uniform(2.5, upper)
        slot = Slot(
            start=START + timedelta(hours=start_hours),
            end=START + timedelta(hours=start_hours + 1),
        )
        placements[task.id] = Placement(task=task, slot=slot, authority=Authority.SERVER)
    return World(now=START, placements=placements)


def current_task(task_id: str, tasks: list[Task], world: World) -> Task:
    placement = world.placements.get(task_id)
    if placement is not None:
        return placement.task
    return next(t for t in tasks if t.id == task_id)


def propose_marginal(task: Task, world: World, rng: random.Random) -> Proposal:
    """Small toward-deadline shift on the current slot. ~2-8% score
    improvement -- exactly the band the threshold gate is built to filter."""
    current = world.current_slot(task.id)
    now = world.now
    if current is None:
        start = now + timedelta(hours=1)
        return Proposal(
            task=task,
            proposed_slot=Slot(start=start, end=start + timedelta(hours=1)),
            authority=Authority.SERVER,
        )
    shift = rng.uniform(0.5, 2.0)
    new_start = current.start + timedelta(hours=shift)
    deadline_floor = task.deadline - timedelta(hours=1.1)
    if new_start > deadline_floor:
        new_start = deadline_floor
    earliest = now + timedelta(hours=0.1)
    if new_start < earliest:
        new_start = earliest
    return Proposal(
        task=task,
        proposed_slot=Slot(start=new_start, end=new_start + timedelta(hours=1)),
        authority=Authority.SERVER,
    )


def propose_mixed(task: Task, world: World, rng: random.Random) -> Proposal:
    """50/50 between a small toward-deadline shift and a large corrective
    move (jump to a slot ~2-3h before the deadline). Approximates what
    an optimizer might emit: mostly noise, occasionally a real fix."""
    if rng.random() < 0.5:
        return propose_marginal(task, world, rng)
    now = world.now
    deadline_hours = (task.deadline - now).total_seconds() / 3600
    target_offset = max(0.5, deadline_hours - rng.uniform(2.0, 3.0))
    start = now + timedelta(hours=target_offset)
    return Proposal(
        task=task,
        proposed_slot=Slot(start=start, end=start + timedelta(hours=1)),
        authority=Authority.SERVER,
    )


def propose_adversarial(task: Task, world: World, rng: random.Random) -> Proposal:
    """Tiny toward-deadline shifts (0.3-0.8h) -- each one a small fraction
    of a percent improvement. The 'many nudges' failure mode."""
    current = world.current_slot(task.id)
    now = world.now
    if current is None:
        return propose_marginal(task, world, rng)
    shift = rng.uniform(0.3, 0.8)
    new_start = current.start + timedelta(hours=shift)
    deadline_floor = task.deadline - timedelta(hours=1.1)
    if new_start > deadline_floor:
        new_start = deadline_floor
    earliest = now + timedelta(hours=0.1)
    if new_start < earliest:
        new_start = earliest
    return Proposal(
        task=task,
        proposed_slot=Slot(start=new_start, end=new_start + timedelta(hours=1)),
        authority=Authority.SERVER,
    )


WORKLOADS = [
    Workload("quiet", propose_marginal, 0.10, "#2ca02c"),
    Workload("chaotic", propose_mixed, 0.80, "#ff7f0e"),
    Workload("adversarial", propose_adversarial, 0.80, "#9467bd"),
]


def deviation_hours(world: World) -> float:
    diffs = []
    for placement in world.placements.values():
        ideal_end = placement.task.deadline - timedelta(hours=IDEAL_END_BUFFER_HOURS)
        diff = abs((placement.slot.end - ideal_end).total_seconds()) / 3600
        diffs.append(diff)
    return statistics.fmean(diffs) if diffs else 0.0


def run(
    seed: int,
    threshold: float,
    proposer: Proposer,
    proposal_rate: float,
    accept: bool = True,
) -> tuple[float, float]:
    rng = random.Random(seed)
    tasks = make_tasks(rng)
    world = initial_world(tasks, rng)
    scheduler = Scheduler(
        weights=ScoreWeights(stability=1.0),
        move_threshold=threshold,
        freeze_hours=2.0,
    )

    moves = 0
    n_ticks = (SIM_HOURS * 60) // TICK_MINUTES
    for tick in range(n_ticks):
        now = START + timedelta(minutes=TICK_MINUTES * tick)
        world = World(
            now=now,
            placements=world.placements,
            completed_dependencies=world.completed_dependencies,
        )
        if rng.random() >= proposal_rate:
            continue
        task = rng.choice(tasks)
        task = current_task(task.id, tasks, world)
        proposal = proposer(task, world, rng)
        if not accept:
            continue
        outcome = scheduler.evaluate(proposal, world)
        if outcome.decision in (Decision.APPLY, Decision.DEADLINE_OVERRIDE):
            world, _ = scheduler.apply(proposal, world, now)
            moves += 1

    return moves / len(tasks), deviation_hours(world)


def aggregate(
    workload: Workload, threshold: float
) -> tuple[float, float, float, float]:
    notifs, devs = [], []
    for seed in SEEDS:
        n, d = run(seed, threshold, workload.proposer, workload.proposal_rate)
        notifs.append(n)
        devs.append(d)
    return (
        statistics.fmean(notifs),
        statistics.stdev(notifs) if len(notifs) > 1 else 0.0,
        statistics.fmean(devs),
        statistics.stdev(devs) if len(devs) > 1 else 0.0,
    )


def main() -> None:
    print(
        f"{'workload':>12}  {'thr':>5}  {'notif μ':>8}  "
        f"{'notif σ':>8}  {'dev μ':>7}  {'dev σ':>6}"
    )
    print("-" * 60)

    by_workload: dict[str, list[tuple[float, float, float, float, float]]] = {}
    for wl in WORKLOADS:
        rows = []
        for thr in THRESHOLDS:
            n_mu, n_sd, d_mu, d_sd = aggregate(wl, thr)
            rows.append((thr, n_mu, n_sd, d_mu, d_sd))
            print(
                f"{wl.name:>12}  {thr:>5.2f}  {n_mu:>8.3f}  "
                f"{n_sd:>8.3f}  {d_mu:>7.3f}  {d_sd:>6.3f}"
            )
        by_workload[wl.name] = rows

    devs = []
    for seed in SEEDS:
        rng = random.Random(seed)
        tasks = make_tasks(rng)
        world = initial_world(tasks, rng)
        devs.append(deviation_hours(world))
    do_nothing = (
        0.0,
        0.0,
        statistics.fmean(devs),
        statistics.stdev(devs),
    )
    print(
        f"{'do nothing':>12}  {'-':>5}  "
        f"{do_nothing[0]:>8.3f}  {do_nothing[1]:>8.3f}  "
        f"{do_nothing[2]:>7.3f}  {do_nothing[3]:>6.3f}"
    )

    out = Path(__file__).parent / "sim_pareto_workloads.png"
    plot(by_workload, do_nothing, out)
    print(f"\nchart written to {out}")


def plot(by_workload, do_nothing, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6.5))

    for wl in WORKLOADS:
        rows = by_workload[wl.name]
        xs = [r[1] for r in rows]
        xerr = [r[2] for r in rows]
        ys = [r[3] for r in rows]
        yerr = [r[4] for r in rows]
        ax.errorbar(
            xs,
            ys,
            xerr=xerr,
            yerr=yerr,
            fmt="-o",
            color=wl.color,
            ecolor=wl.color,
            elinewidth=1,
            capsize=3,
            alpha=0.85,
            label=wl.name,
        )
        # Ring the default point on every curve, but only label the
        # chaotic one — quiet and adversarial defaults sit on top of
        # do-nothing and produce an unreadable label pile-up.
        for thr, x, _, y, _ in rows:
            if abs(thr - DEFAULT_THRESHOLD) < 1e-9:
                ax.plot(
                    x,
                    y,
                    marker="o",
                    markersize=12,
                    markerfacecolor="none",
                    markeredgecolor=wl.color,
                    markeredgewidth=2,
                )
                if wl.name == "chaotic":
                    ax.annotate(
                        f"  {wl.name} @ 0.15",
                        (x, y),
                        xytext=(8, 0),
                        textcoords="offset points",
                        fontsize=9,
                        color=wl.color,
                    )

    ax.errorbar(
        [do_nothing[0]],
        [do_nothing[2]],
        xerr=[do_nothing[1]],
        yerr=[do_nothing[3]],
        fmt="s",
        color="#d62728",
        ecolor="#d62728",
        elinewidth=1,
        capsize=3,
        markersize=8,
        label="do nothing",
    )

    ax.annotate(
        "quiet & adversarial @ 0.15 ≈ do nothing",
        xy=(do_nothing[0], do_nothing[2]),
        xytext=(0.15, do_nothing[2] + 0.15),
        fontsize=9,
        color="#444",
        arrowprops=dict(
            arrowstyle="->", color="#444", lw=1, shrinkA=0, shrinkB=6
        ),
    )

    ax.set_xlabel("notifications per task per day  ←  calmer")
    ax.set_ylabel("schedule deviation (hours)  ←  better quality")
    ax.set_title(
        "Churn vs. quality across workloads (50 seeds, ringed point = library default 0.15)"
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", framealpha=0.9)
    fig.text(
        0.5,
        0.02,
        "Adversarial error bars are wide because the proposer is stochastic; "
        "the flatness of the curve is real, the wobble is sampling noise.",
        ha="center",
        fontsize=8.5,
        color="#555",
        style="italic",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=120)


if __name__ == "__main__":
    main()
