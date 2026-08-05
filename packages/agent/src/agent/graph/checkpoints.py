"""State snapshots per super-step, one thread per run.

LangGraph writes the whole state after every node. Kept, that turns a finished
run from a number into something you can step through: what the queue looked
like before this chunk, what the model proposed, what survived verification.
An interrupted run also resumes from the last step instead of restarting.

Writing over an old snapshot branches the thread there rather than overwriting
it: the new checkpoint records the old one as its parent, so the history is a
tree and the original line survives being second-guessed.

Stored beside the run's chunks and spans, in its own file. A run's history is
its own -- nothing here is shared between runs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from .state import RESET

#: State fields that are large and reconstructible from the store. A snapshot is
#: for seeing where the run was, not for holding a second copy of the findings.
BULKY = ("candidates", "located", "confirmed", "verdicts", "context_text")

#: Enough to see the shape of a step without rendering a wall of JSON.
PREVIEW_ITEMS = 5


def checkpoint_saver(path: Path) -> SqliteSaver:
    """A saver on the run's own file.

    ``check_same_thread=False`` because the inspection runs on a worker thread
    while the API reads history from the request thread.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return SqliteSaver(conn)


def summarise(values: Any) -> dict[str, Any]:
    """The state of one step, with the bulky parts counted rather than copied."""
    if not isinstance(values, dict):
        return {"value": str(values)[:2000]}

    out: dict[str, Any] = {}
    for key, value in values.items():
        if value == RESET:
            # `plan` empties the per-wave channels by writing a sentinel the
            # reducers understand. Shown as what it means, not as the token:
            # nobody reading a trace should have to know that spelling.
            out[key] = {"cleared": True}
        elif key in BULKY and isinstance(value, list):
            out[key] = {"count": len(value)}
        elif key == "pending" and isinstance(value, list):
            # The queue is the run's remaining work: its length is the progress
            # bar, and its head is the chunk about to be inspected.
            out[key] = {"remaining": len(value), "next": value[:PREVIEW_ITEMS]}
        else:
            out[key] = value
    return out


def _id(config: Any) -> str | None:
    return ((config or {}).get("configurable") or {}).get("checkpoint_id")


def _open(path: Path) -> tuple[Any, SqliteSaver]:
    """A graph over this run's saver, compiled purely to read or write history.

    The nodes only close over what they are given and nothing runs here, so
    hollow dependencies are enough.
    """
    from .build import build_graph, hollow_deps

    saver = checkpoint_saver(path)
    return build_graph(hollow_deps(), checkpointer=saver), saver


def _step(snapshot: Any, full: bool, wrote: list[str]) -> dict[str, Any]:
    """One snapshot, flattened for the wire."""
    metadata = snapshot.metadata or {}
    return {
        "checkpoint_id": _id(snapshot.config),
        # The line this step came from. With this the history reads as a tree,
        # which is what a branch makes it.
        "parent_checkpoint_id": _id(snapshot.parent_config),
        "step": metadata.get("step"),
        "source": metadata.get("source"),
        "node": wrote[0] if wrote else None,
        "nodes": wrote,
        "next": list(snapshot.next),
        "created_at": snapshot.created_at,
        "values": snapshot.values if full else summarise(snapshot.values),
    }


def read_history(path: Path, thread_id: str, limit: int = 500, full: bool = False) -> list[dict[str, Any]]:
    """Every checkpoint of one run, oldest first.

    LangGraph yields newest first, which is the wrong way round for reading a
    run as a sequence of steps.
    """
    if not path.exists():
        return []

    app, saver = _open(path)
    try:
        snapshots = list(app.get_state_history({"configurable": {"thread_id": thread_id}}, limit=limit))
    finally:
        saver.conn.close()

    # Which node produced a checkpoint is not recorded anywhere; ``next`` is the
    # other way round, naming what a checkpoint is *about to* run. Following each
    # snapshot's parent pointer turns that into the answer: whatever was queued
    # at the parent is what wrote the child. The pointer is followed rather than
    # the list order assumed, so a branch resolves as well as a straight line.
    queued = {_id(snapshot.config): list(snapshot.next) for snapshot in snapshots}
    return [_step(snapshot, full, queued.get(_id(snapshot.parent_config), [])) for snapshot in reversed(snapshots)]


def read_state(path: Path, thread_id: str, checkpoint_id: str | None = None) -> dict[str, Any] | None:
    """One checkpoint's state in full.

    The history summarises the bulky fields, which is right for a timeline and
    wrong for an editor: you cannot edit a count back into a list.
    """
    if not path.exists():
        return None

    app, saver = _open(path)
    try:
        snapshot = app.get_state(_config(thread_id, checkpoint_id))
        wrote = _wrote(app, snapshot)
    finally:
        saver.conn.close()

    if not snapshot.values and snapshot.created_at is None:
        return None
    return _step(snapshot, True, wrote)


def _wrote(app: Any, snapshot: Any) -> list[str]:
    """The node that produced one snapshot, read off its parent's queue."""
    if not snapshot.parent_config:
        return []
    return list(app.get_state(snapshot.parent_config).next)


def write_state(
    path: Path,
    thread_id: str,
    values: dict[str, Any],
    checkpoint_id: str | None = None,
    as_node: str | None = None,
) -> str | None:
    """Write state over a checkpoint and return the new checkpoint's id.

    Against an earlier checkpoint this branches: the write lands as a child of
    that point, and running from it explores a different course without
    disturbing the one already recorded.
    """
    if not path.exists():
        raise FileNotFoundError(f"no checkpoints for thread {thread_id}")

    app, saver = _open(path)
    try:
        config = _config(thread_id, checkpoint_id)
        if as_node is None:
            # LangGraph needs to know whose write this stands in for: it decides
            # where the graph goes next. Standing in for whoever wrote this
            # checkpoint puts it back on the course it was already on.
            wrote = _wrote(app, app.get_state(config))
            as_node = wrote[0] if wrote else None
        written = app.update_state(config, values, as_node=as_node)
    finally:
        saver.conn.close()

    return ((written or {}).get("configurable") or {}).get("checkpoint_id")


def _config(thread_id: str, checkpoint_id: str | None) -> dict[str, Any]:
    # ``checkpoint_ns`` is spelled out because writing a checkpoint requires it
    # and reading one does not. There are no subgraphs here, so it is the root
    # namespace either way.
    configurable: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": ""}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}
