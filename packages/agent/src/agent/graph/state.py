"""State for the inspection graph.

Deliberately small and JSON-serialisable. The chunk store, the model client and
the run root are *not* in here -- they are injected into the nodes when the graph
is built. Putting a SQLite connection in graph state would make the state
unserialisable and defeat checkpointing, and duplicating chunk bodies into it
would balloon every checkpoint with data already on disk.

What is in state is the run's position and its tallies: which chunks remain, what
the current one produced, and the counters the progress UI reports.
"""

from __future__ import annotations

from typing import Any, TypedDict


class InspectionState(TypedDict, total=False):
    """One inspection run, in flight."""

    #: Chunk ids not yet inspected, in topological order (callees first).
    pending: list[str]
    #: The chunk being worked on, or None when the queue is drained.
    current: str | None
    #: Assembled context for ``current``; rebuilt each iteration.
    context_text: str
    #: Serialised CandidateFinding objects from the analyse call.
    candidates: list[dict[str, Any]]
    #: Serialised Finding objects that survived locating, awaiting verification.
    located: list[dict[str, Any]]
    #: Serialised Finding objects that survived verification, for this chunk.
    confirmed: list[dict[str, Any]]
    #: Running tallies, mirroring :class:`agent.schema.RunStats`.
    stats: dict[str, int]


def initial_state(order: list[str], chunks_total: int, stats: dict[str, int] | None = None) -> InspectionState:
    base = {
        "files_indexed": 0,
        "files_skipped": 0,
        "chunks_total": chunks_total,
        "chunks_inspected": 0,
        "chunks_cached": 0,
        "candidates": 0,
        "dropped_unlocatable": 0,
        "refuted": 0,
    }
    if stats:
        base.update(stats)
    return InspectionState(
        pending=list(order),
        current=None,
        context_text="",
        candidates=[],
        located=[],
        confirmed=[],
        stats=base,
    )
