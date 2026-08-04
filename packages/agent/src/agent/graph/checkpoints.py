"""State snapshots per super-step, one thread per run.

LangGraph writes the whole state after every node. Kept, that turns a finished
run from a number into something you can step through: what the queue looked
like before this chunk, what the model proposed, what survived verification.
An interrupted run also resumes from the last step instead of restarting.

Stored beside the run's chunks and spans, in its own file. A run's history is
its own -- nothing here is shared between runs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

#: State fields that are large and reconstructible from the store. A snapshot is
#: for seeing where the run was, not for holding a second copy of the findings.
BULKY = ("candidates", "located", "confirmed", "context_text")

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


def _summarise(values: Any) -> dict[str, Any]:
    """The state of one step, with the bulky parts counted rather than copied."""
    if not isinstance(values, dict):
        return {"value": str(values)[:2000]}

    out: dict[str, Any] = {}
    for key, value in values.items():
        if key in BULKY and isinstance(value, list):
            out[key] = {"count": len(value)}
        elif key == "pending" and isinstance(value, list):
            # The queue is the run's remaining work: its length is the progress
            # bar, and its head is the chunk about to be inspected.
            out[key] = {"remaining": len(value), "next": value[:PREVIEW_ITEMS]}
        else:
            out[key] = value
    return out


def read_history(path: Path, thread_id: str, limit: int = 500) -> list[dict[str, Any]]:
    """Every checkpoint of one run, oldest first.

    LangGraph yields newest first, which is the wrong way round for reading a
    run as a sequence of steps.
    """
    if not path.exists():
        return []

    from .build import build_graph, hollow_deps

    saver = checkpoint_saver(path)
    try:
        app = build_graph(hollow_deps(), checkpointer=saver)
        snapshots = list(app.get_state_history({"configurable": {"thread_id": thread_id}}, limit=limit))
    finally:
        saver.conn.close()

    steps: list[dict[str, Any]] = []
    previous: tuple[str, ...] = ()
    for snapshot in reversed(snapshots):
        meta = snapshot.metadata or {}
        pending = tuple(snapshot.next)
        steps.append(
            {
                "checkpoint_id": (snapshot.config.get("configurable") or {}).get("checkpoint_id"),
                "step": meta.get("step"),
                "source": meta.get("source"),
                # The metadata does not name the node that wrote this state, so
                # it is read off the previous snapshot: what was queued to run
                # then is what produced the state now.
                "node": previous[0] if previous else None,
                "next": list(pending),
                "created_at": snapshot.created_at,
                "values": _summarise(snapshot.values),
            }
        )
        previous = pending
    return steps
