"""The run's plan: what it means to do, and what it has done.

`index/order.py` decides the traversal and `plan` pops from it. That is not
changing -- it is the property `build.py` calls the reason two runs over one
tree are comparable, and an ordering a model can rewrite is an ordering nobody
can diff. What is added is that the traversal becomes *visible*: a row per unit
saying where the index put it, where the run has got to, and why it is there at
all.

The advisory mode does not hand the model the wheel. It may emit events, and an
event is a request -- `defer`, `skip`, `raise_priority`, `split` -- applied here
by a reducer in a fixed order. So:

* the plan is a fold over (computed order, event log), and nothing else;
* replaying the fold gives the same plan, because `seq` is assigned on write
  rather than taken from the order a model happened to emit things in;
* every event that changed anything is on the trace beside the model output that
  asked for it.

The obvious alternative -- let `replan` return the next chunk id -- was rejected.
It is fewer moving parts and it makes the run unreproducible: two runs over one
tree would diverge on the model's mood, and no report could be diffed against
another. Events are the version of this that keeps the invariant.

`split` records an intent and does not subdivide a unit. A chunk is content-
addressed -- its id *is* its body -- so splitting one would produce ids no index
ever wrote, and a plan referring to units that do not exist is worse than a plan
that admits it wanted to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from ..config import AgentConfig
from ..db import PlanEventRow, PlanItem, session_factory

log = logging.getLogger(__name__)

PlanStatus = Literal["pending", "running", "done", "skipped", "blocked"]
PlanEventKind = Literal["defer", "skip", "raise_priority", "split"]

#: Every kind the reducer understands. A `replan` that proposes anything else is
#: proposing a change to traversal by another name, so it is dropped and counted
#: rather than guessed at.
EVENT_KINDS: tuple[str, ...] = ("defer", "skip", "raise_priority", "split")

#: How far one event moves an item. Deferring pushes it behind its neighbours
#: without leaving the order; raising pulls it in front of them. Bounded on
#: purpose: an event that could move an item arbitrarily far is a reordering,
#: and a reordering is the thing this design refuses to allow.
STEP = 1


@dataclass(frozen=True)
class PlanEvent:
    """A request to change the plan. Not a change to it."""

    kind: PlanEventKind
    target: str
    reason: str = ""
    span_id: str | None = None


@dataclass(frozen=True)
class Item:
    """One planned unit, as read back."""

    chunk_id: str
    status: str
    reason: str
    order_key: int
    priority: int


class PlanStore:
    """The plan of one run. Scoped by run id, like everything else here."""

    def __init__(self, run_id: str, config: AgentConfig | None = None) -> None:
        self.run_id = run_id
        self._sessions = session_factory(config)

    # -- writing ------------------------------------------------------------

    def seed(self, order: Sequence[str], reason: str = "computed order") -> int:
        """Write the computed traversal down as the plan.

        Idempotent, and that matters: a resumed run seeds again, and a seed that
        reset every status would forget which units were already done. So this
        inserts what is missing and leaves what is there.
        """
        rows = [
            {
                "run_id": self.run_id,
                "chunk_id": chunk_id,
                "status": "pending",
                "reason": reason,
                "order_key": position,
                "priority": 0,
            }
            for position, chunk_id in enumerate(order)
        ]
        if not rows:
            return 0
        with self._sessions() as session:
            session.execute(insert(PlanItem).on_conflict_do_nothing(), rows)
            session.commit()
        return len(rows)

    def mark(self, chunk_ids: Iterable[str], status: PlanStatus) -> None:
        ids = list(chunk_ids)
        if not ids:
            return
        with self._sessions() as session:
            session.execute(
                insert(PlanItem)
                .values([{"run_id": self.run_id, "chunk_id": c, "status": status, "order_key": 0} for c in ids])
                .on_conflict_do_update(index_elements=["run_id", "chunk_id"], set_={"status": status})
            )
            session.commit()

    def record(self, events: Sequence[PlanEvent]) -> list[PlanEvent]:
        """Append events to the log and apply them. Returns what was applied.

        Applied *here*, in one place, rather than by whoever emitted them --
        which is what makes "a fixed order" a property of the store instead of a
        convention every caller has to keep.
        """
        usable = [event for event in events if event.kind in EVENT_KINDS]
        if not usable:
            return []

        with self._sessions() as session:
            start = session.scalar(
                select(func.coalesce(func.max(PlanEventRow.seq), -1)).where(PlanEventRow.run_id == self.run_id)
            )
            next_seq = int(start or -1) + 1
            session.execute(
                insert(PlanEventRow),
                [
                    {
                        "run_id": self.run_id,
                        "seq": next_seq + offset,
                        "kind": event.kind,
                        "target": event.target,
                        "reason": event.reason,
                        "span_id": event.span_id,
                    }
                    for offset, event in enumerate(usable)
                ],
            )
            session.commit()

        self._apply(usable)
        return usable

    def _apply(self, events: Sequence[PlanEvent]) -> None:
        """Fold events onto the items. The only writer of priority and skip."""
        with self._sessions() as session:
            for event in events:
                item = session.get(PlanItem, (self.run_id, event.target))
                if item is None:
                    # An event about a unit no index produced. Dropped rather
                    # than inserted: a plan is a statement about a tree, and a
                    # row for a chunk that does not exist is not one.
                    log.debug("plan: event %s names unknown chunk %s", event.kind, event.target)
                    continue
                if event.kind == "skip":
                    item.status = "skipped"
                elif event.kind == "defer":
                    item.priority -= STEP
                elif event.kind == "raise_priority":
                    item.priority += STEP
                elif event.kind == "split":
                    # Recorded, not acted on. See the module docstring: a chunk
                    # id is its content, so there is no smaller unit to point at.
                    item.reason = (item.reason + " | split requested").strip(" |")
                if event.reason and event.kind != "split":
                    item.reason = event.reason
            session.commit()

    def clear(self) -> None:
        """Forget the plan and its log, for a fresh start."""
        with self._sessions() as session:
            session.execute(delete(PlanItem).where(PlanItem.run_id == self.run_id))
            session.execute(delete(PlanEventRow).where(PlanEventRow.run_id == self.run_id))
            session.commit()

    # -- reading ------------------------------------------------------------

    def items(self) -> list[Item]:
        """Every item, in plan order: raised first, then the computed order.

        `-priority` before `order_key`, so an untouched plan reads back exactly
        as the index wrote it -- every priority is zero, and the sort collapses
        to the order key alone. That is what makes `computed` mode identical
        rather than merely equivalent.
        """
        with self._sessions() as session:
            rows = session.scalars(
                select(PlanItem)
                .where(PlanItem.run_id == self.run_id)
                .order_by(PlanItem.priority.desc(), PlanItem.order_key)
            ).all()
        return [
            Item(
                chunk_id=row.chunk_id,
                status=row.status,
                reason=row.reason or "",
                order_key=row.order_key,
                priority=row.priority,
            )
            for row in rows
        ]

    def events(self) -> list[PlanEvent]:
        """The log, in the order it was applied."""
        with self._sessions() as session:
            rows = session.scalars(
                select(PlanEventRow).where(PlanEventRow.run_id == self.run_id).order_by(PlanEventRow.seq)
            ).all()
        return [PlanEvent(kind=r.kind, target=r.target, reason=r.reason or "", span_id=r.span_id) for r in rows]

    def pending(self) -> list[str]:
        """The queue, as the graph should see it."""
        return [item.chunk_id for item in self.items() if item.status in ("pending", "running")]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items():
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    def close(self) -> None:
        """Nothing to close: sessions are per-operation. Kept because callers
        pair it with the constructor, as `ChunkStore` does."""


def apply_events(order: Sequence[str], events: Sequence[PlanEvent]) -> list[str]:
    """The same fold, in memory, over a bare order.

    Used by the replay test and by anything wanting to know what a log would do
    without a database in the way. It has to agree with `PlanStore._apply`, and
    the test that asserts they do is the reason this is written once as a fold
    rather than twice as two loops.
    """
    priority = {chunk_id: 0 for chunk_id in order}
    skipped: set[str] = set()
    position = {chunk_id: index for index, chunk_id in enumerate(order)}

    for event in events:
        if event.kind not in EVENT_KINDS or event.target not in position:
            continue
        if event.kind == "skip":
            skipped.add(event.target)
        elif event.kind == "defer":
            priority[event.target] -= STEP
        elif event.kind == "raise_priority":
            priority[event.target] += STEP

    remaining = [chunk_id for chunk_id in order if chunk_id not in skipped]
    return sorted(remaining, key=lambda chunk_id: (-priority[chunk_id], position[chunk_id]))
