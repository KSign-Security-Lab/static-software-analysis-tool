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
EVENT_KINDS: tuple[str, ...] = ("defer", "skip", "raise_priority", "split")
STEP = 1


@dataclass(frozen=True)
class PlanEvent:
    kind: PlanEventKind
    target: str
    reason: str = ""
    span_id: str | None = None


@dataclass(frozen=True)
class Item:
    chunk_id: str
    status: str
    reason: str
    order_key: int
    priority: int


class PlanStore:
    def __init__(self, run_id: str, config: AgentConfig | None = None) -> None:
        self.run_id = run_id
        self._sessions = session_factory(config)

    def seed(self, order: Sequence[str], reason: str = "computed order") -> int:
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
        with self._sessions() as session:
            for event in events:
                item = session.get(PlanItem, (self.run_id, event.target))
                if item is None:
                    log.debug("plan: event %s names unknown chunk %s", event.kind, event.target)
                    continue
                if event.kind == "skip":
                    item.status = "skipped"
                elif event.kind == "defer":
                    item.priority -= STEP
                elif event.kind == "raise_priority":
                    item.priority += STEP
                elif event.kind == "split":
                    item.reason = (item.reason + " | split requested").strip(" |")
                if event.reason and event.kind != "split":
                    item.reason = event.reason
            session.commit()

    def clear(self) -> None:
        with self._sessions() as session:
            session.execute(delete(PlanItem).where(PlanItem.run_id == self.run_id))
            session.execute(delete(PlanEventRow).where(PlanEventRow.run_id == self.run_id))
            session.commit()

    def items(self) -> list[Item]:
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
        with self._sessions() as session:
            rows = session.scalars(
                select(PlanEventRow).where(PlanEventRow.run_id == self.run_id).order_by(PlanEventRow.seq)
            ).all()
        return [PlanEvent(kind=r.kind, target=r.target, reason=r.reason or "", span_id=r.span_id) for r in rows]

    def pending(self) -> list[str]:
        return [item.chunk_id for item in self.items() if item.status in ("pending", "running")]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items():
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    def close(self) -> None:
        pass


# The same fold as `PlanStore._apply`, in memory. The two must agree; a test asserts it.
def apply_events(order: Sequence[str], events: Sequence[PlanEvent]) -> list[str]:
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
