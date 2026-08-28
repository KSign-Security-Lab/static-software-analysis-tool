"""State for the inspection graph.

Deliberately small and JSON-serialisable. The chunk store, the model client and
the run root are *not* in here -- they are injected into the nodes when the graph
is built. Putting a SQLite connection in graph state would make the state
unserialisable and defeat checkpointing, and duplicating chunk bodies into it
would balloon every checkpoint with data already on disk.

What is in state is the run's position and its tallies: which chunks remain, what
the current wave produced, and the counters the progress UI reports.

Most channels carry a reducer. A wave of chunks is analysed by several nodes at
once and they all write here; without a reducer LangGraph refuses the concurrent
update, and with the wrong one the last writer wins and three specialists' work
disappears. The reducers also have to *forget*: each wave starts clean, which is
what :data:`RESET` is for.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

#: Written in place of a value to mean "discard what was there".
#:
#: An additive reducer has no other way to be told that the previous wave is
#: over. Spelled as a string so it survives a round trip through the checkpoint
#: file, which JSON-encodes everything it is given.
RESET = "__reset__"


def concat(old: list[Any], new: list[Any] | str) -> list[Any]:
    """Append, unless told to start over.

    The sentinel is recognised by type, not by value: a list can never be the
    reset marker, so `isinstance` says exactly what is meant and does not have
    to reason about a string that happens to compare equal.
    """
    if isinstance(new, str):
        return []
    return [*old, *new]


def merge(old: dict[str, Any], new: dict[str, Any] | str) -> dict[str, Any]:
    """Later keys win; a wave's worth of writers each own different keys."""
    if isinstance(new, str):
        return {}
    return {**old, **new}


def add_counts(old: dict[str, int], new: dict[str, int] | str) -> dict[str, int]:
    """Sum the tallies rather than replacing them.

    Four specialists each finishing with ``candidates: 2`` mean six candidates
    were found, not two. Under the old sequential loop a node could read the
    running total and write it back; concurrently that is a lost update, so
    nodes now report only their own contribution and the sum happens here.
    """
    if isinstance(new, str):
        return {}
    merged = dict(old)
    for key, value in new.items():
        merged[key] = merged.get(key, 0) + value
    return merged


class InspectionState(TypedDict, total=False):
    """One inspection run, in flight."""

    #: Chunk ids not yet inspected, in topological order (callees first).
    pending: list[str]
    #: The chunks being worked on together -- all at one call depth, so none of
    #: them needs another's note.
    wave: list[str]
    #: The first of ``wave``. Kept because a great deal reads it, and because a
    #: width of one is still the ordinary case for a small tree.
    current: str | None
    #: Assembled context per chunk in the wave; rebuilt each iteration.
    packs: Annotated[dict[str, str], merge]
    #: Chunk id to the screening verdict: whether to analyse it, and by whom.
    triaged: Annotated[dict[str, Any], merge]
    #: Chunk id to the stretches of it worth reading closely.
    #:
    #: Keyed rather than a list, and that is load-bearing: `specialists` is
    #: evaluated once per task and must see only its own chunk's regions. A
    #: `concat` list would show it every other unit's as well, and it would fan
    #: a specialist out over all of them.
    scouted: Annotated[dict[str, Any], merge]
    #: Serialised CandidateFinding objects, each tagged with its chunk and lens.
    candidates: Annotated[list[dict[str, Any]], concat]
    #: Serialised Finding objects that survived locating, awaiting verification.
    located: Annotated[list[dict[str, Any]], concat]
    #: One verdict per located finding, from the fanned-out verify pass.
    verdicts: Annotated[list[dict[str, Any]], concat]
    #: Serialised Finding objects that survived verification, for this wave.
    confirmed: Annotated[list[dict[str, Any]], concat]
    #: Running tallies, mirroring :class:`agent.schema.RunStats`.
    stats: Annotated[dict[str, int], add_counts]


#: Everything a new wave has to forget before it starts.
WAVE_CHANNELS = ("packs", "triaged", "scouted", "candidates", "located", "verdicts", "confirmed")


def clear_wave() -> dict[str, Any]:
    """The update that empties the per-wave channels."""
    return {channel: RESET for channel in WAVE_CHANNELS}


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
        "triaged_out": 0,
        "regions": 0,
    }
    if stats:
        base.update(stats)
    return InspectionState(
        pending=list(order),
        wave=[],
        current=None,
        packs={},
        triaged={},
        scouted={},
        candidates=[],
        located=[],
        verdicts=[],
        confirmed=[],
        stats=base,
    )
