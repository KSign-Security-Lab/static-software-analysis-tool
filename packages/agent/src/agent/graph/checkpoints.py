"""State snapshots per super-step, one thread per run.

LangGraph writes the whole state after every node. Kept, that turns a finished
run from a number into something you can step through: what the queue looked
like before this chunk, what the model proposed, what survived verification.
An interrupted run also resumes from the last step instead of restarting.

Writing over an old snapshot branches the thread there rather than overwriting
it: the new checkpoint records the old one as its parent, so the history is a
tree and the original line survives being second-guessed.

Stored beside the run's chunks and spans, in the same database. LangGraph keys
its own tables by ``thread_id``, and the thread is the run id -- so a run's
history is its own without a file of its own.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection

from .state import RESET

#: State fields that are large and reconstructible from the store. A snapshot is
#: for seeing where the run was, not for holding a second copy of the findings.
BULKY = ("candidates", "located", "confirmed", "verdicts", "context_text")

#: Enough to see the shape of a step without rendering a wall of JSON.
PREVIEW_ITEMS = 5


def checkpoint_saver(database_url: str) -> tuple[Connection, PostgresSaver]:
    """A saver and the connection it owns.

    The connection comes back with it because the caller has to close it, and
    LangGraph's saver does not own its own lifetime. `autocommit` because
    `setup()` issues DDL, and psycopg would otherwise leave it in a transaction
    that the first reader blocks on.

    `setup()` on every open is deliberate and cheap: it is `CREATE TABLE IF NOT
    EXISTS`, and it is what stops the first run of a fresh database failing on
    tables the application schema does not own.
    """
    conn = Connection.connect(_dsn(database_url), autocommit=True, row_factory=_dict_row())
    saver = PostgresSaver(conn)
    saver.setup()
    return conn, saver


def _dsn(database_url: str) -> str:
    """SQLAlchemy spells the driver into the URL; psycopg wants it left out."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


def _dict_row() -> Any:
    from psycopg.rows import dict_row

    return dict_row


def clear_thread(database_url: str, thread_id: str) -> None:
    """Forget one run's history, before a *fresh* inspection.

    Was deleting the run's checkpoint file. The tables are shared between runs
    now, so it is a delete keyed by thread -- which is also why it names every
    table rather than dropping anything.
    """
    conn = Connection.connect(_dsn(database_url), autocommit=True)
    try:
        with conn.cursor() as cur:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                cur.execute(f"DELETE FROM {table} WHERE thread_id = %s", (thread_id,))
    except Exception:
        # A database that has never had a run has no checkpoint tables yet, and
        # "nothing to clear" is the correct outcome rather than an error.
        pass
    finally:
        conn.close()


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


def _open(database_url: str) -> tuple[Any, Connection]:
    """A graph over this run's saver, compiled purely to read or write history.

    The nodes only close over what they are given and nothing runs here, so
    hollow dependencies are enough.
    """
    from .build import build_graph, hollow_deps

    conn, saver = checkpoint_saver(database_url)
    return build_graph(hollow_deps(), checkpointer=saver), conn


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


def read_history(database_url: str, thread_id: str, limit: int = 500, full: bool = False) -> list[dict[str, Any]]:
    """Every checkpoint of one run, oldest first.

    LangGraph yields newest first, which is the wrong way round for reading a
    run as a sequence of steps.
    """
    app, conn = _open(database_url)
    try:
        snapshots = list(app.get_state_history({"configurable": {"thread_id": thread_id}}, limit=limit))
    finally:
        conn.close()

    # Which node produced a checkpoint is not recorded anywhere; ``next`` is the
    # other way round, naming what a checkpoint is *about to* run. Following each
    # snapshot's parent pointer turns that into the answer: whatever was queued
    # at the parent is what wrote the child. The pointer is followed rather than
    # the list order assumed, so a branch resolves as well as a straight line.
    queued = {_id(snapshot.config): list(snapshot.next) for snapshot in snapshots}
    return [_step(snapshot, full, queued.get(_id(snapshot.parent_config), [])) for snapshot in reversed(snapshots)]


def read_state(database_url: str, thread_id: str, checkpoint_id: str | None = None) -> dict[str, Any] | None:
    """One checkpoint's state in full.

    The history summarises the bulky fields, which is right for a timeline and
    wrong for an editor: you cannot edit a count back into a list.
    """
    app, conn = _open(database_url)
    try:
        snapshot = app.get_state(_config(thread_id, checkpoint_id))
        wrote = _wrote(app, snapshot)
    finally:
        conn.close()

    if not snapshot.values and snapshot.created_at is None:
        return None
    return _step(snapshot, True, wrote)


def _wrote(app: Any, snapshot: Any) -> list[str]:
    """The node that produced one snapshot, read off its parent's queue."""
    if not snapshot.parent_config:
        return []
    return list(app.get_state(snapshot.parent_config).next)


def write_state(
    database_url: str,
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
    app, conn = _open(database_url)
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
        conn.close()

    return ((written or {}).get("configurable") or {}).get("checkpoint_id")


def _config(thread_id: str, checkpoint_id: str | None) -> dict[str, Any]:
    # ``checkpoint_ns`` is spelled out because writing a checkpoint requires it
    # and reading one does not. There are no subgraphs here, so it is the root
    # namespace either way.
    configurable: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": ""}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}
