# stable-scheduler

A scheduling library that optimizes for **stability**, not just optimality.

Most schedulers recompute on every event and surface the locally optimal arrangement immediately. From the user's perspective this looks like chaos. `stable-scheduler` adds the term most planning systems leave out: a penalty for moving recently-placed tasks. Combined with recomputation windows, move thresholds, freeze horizons, and an authority hierarchy, the scheduler resists churn the user would experience as untrustworthy.

> A scoring function that does not include the cost of change is an incomplete objective function.

The companion article: [Why Optimal Scheduling Breaks User Trust](https://arjona.dev/writing/optimal-scheduling).

## Why this exists

In a previous role I shipped a "provably optimal" scheduler that nobody used. Within two weeks every engineer had pinned their tasks manually. The algorithm was correct. The product was broken. The fix was a 5-line change to the scoring function plus four production patterns layered on top. This library is the smallest reusable version of that fix.

## Install

```bash
pip install stable-scheduler
```

(Pre-1.0. API may change. Pin to a version.)

## Quick start

```python
from datetime import datetime, timedelta
from stable_scheduler import Authority, Proposal, Scheduler, Slot, Task, World

now = datetime.now()

task = Task(
    id="draft-q3-plan",
    priority=7,
    deadline=now + timedelta(hours=48),
    last_rescheduled_at=now - timedelta(minutes=15),
)

world = World(now=now)
scheduler = Scheduler(freeze_hours=2.0, move_threshold=0.15)

proposal = Proposal(
    task=task,
    proposed_slot=Slot(start=now + timedelta(hours=5), end=now + timedelta(hours=6)),
    authority=Authority.SERVER,
)

outcome = scheduler.evaluate(proposal, world)
if outcome.decision.value == "apply":
    world, task = scheduler.apply(proposal, world, now)
else:
    print(f"Rejected: {outcome.reason}")
```

## What's in the box

| Module      | What it does                                                                 |
|-------------|------------------------------------------------------------------------------|
| `score`     | Scoring function with the inverse-decay `reschedule_penalty` term most schedulers omit. |
| `threshold` | Move threshold gate. Marginal improvements are rejected; the default is 15%. |
| `freeze`    | Freeze horizon. Near-term tasks are immutable except for hard-deadline overrides. |
| `buffer`    | Recomputation window. Events are batched so the schedule changes at most once per window. |
| `authority` | Priority hierarchy. User pins beat deadline overrides beat the server beats the agent beats offline clients. |
| `scheduler` | Composes the above into a single decision pipeline.                          |

## The decision pipeline

```
proposal -> pin check -> authority check -> freeze check -> hard-deadline override -> threshold check -> apply
```

Every decision (apply or reject) carries a reason string. Wire `on_outcome` to log it — the lessons-learned section of the article is built on this telemetry.

```python
def log_outcome(outcome):
    print(f"{outcome.decision.value}: {outcome.reason}")

scheduler = Scheduler(on_outcome=log_outcome)
```

## Tuning

`STABILITY_WEIGHT` (in `ScoreWeights.stability`) is the parameter you will argue about more than any other. Start high (the default is 1.0). Track manual pin rates as a product health metric. When pin rates climb, the scheduler is churning too much and the weight is too low.

`move_threshold` controls how much improvement is needed to justify a move. 0.15 (15%) is a reasonable default for human-facing planning systems. Real-time dispatch systems may want lower (0.05). Calendars for knowledge workers may want higher (0.25).

`freeze_hours` is how far into the future is locked. 2.0 is the default. A real-time warehouse dispatcher might use 0.25. A weekly sprint planner might use 24.

## Empirical results

`examples/sim_churn.py` runs a synthetic 24-hour workload of optimizer-style proposals through the pipeline at a sweep of `move_threshold` values, across multiple seeds. The two panels compare the library's default reschedule penalty (`stability=1`, left) against the same scheduler with the penalty disabled (`stability=0`, right).

![Pipeline decision composition vs. move_threshold](examples/sim_churn.png)

Read this as a controlled toy, not a benchmark. Two things to notice:

- **The threshold gate dominates.** As `move_threshold` slides right, the red `BLOCKED_BY_THRESHOLD` band swells and the green `apply` band shrinks. By 0.30 the gate is absorbing the vast majority of optimizer-noise proposals.
- **In this workload the stability term contributes a small marginal effect on top of the threshold.** The two panels look almost identical. The reschedule penalty bites hardest when a task has *just* been moved (inverse decay over hours-since-last-move), and this synthetic workload doesn't churn the same task aggressively enough to keep most proposals inside that window. To exercise the term, raise `PROPOSAL_RATE` and/or narrow `pick_task` to focus on already-moved tasks. The shape that does emerge here — small, monotone-positive — is consistent with what you'd want from a production-tier penalty: invisible most of the time, present when needed.

Run `python examples/sim_churn.py` to regenerate.

## What this library does *not* do

- Solve the underlying optimization. Bring your own scoring function or extend `score.compute_score`. This library is about the *stability terms* on top of whatever optimizer you use.
- Persist state. `World` is an in-memory snapshot. Bring your own database.
- Schedule jobs. This is not Celery or Cron. It decides whether a *proposed change* to an existing schedule should become user-visible.
- Handle distributed consensus. If multiple clients propose conflicting changes simultaneously, you need a coordination layer above this library.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
