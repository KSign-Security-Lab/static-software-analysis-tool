from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection

from .state import RESET

BULKY = ("candidates", "located", "confirmed", "verdicts", "context_text")
PREVIEW_ITEMS = 5


def checkpoint_saver(database_url: str) -> tuple[Connection, PostgresSaver]:
    conn = Connection.connect(_dsn(database_url), autocommit=True, row_factory=_dict_row())
    saver = PostgresSaver(conn)
    saver.setup()
    return conn, saver


def _dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://")


def _dict_row() -> Any:
    from psycopg.rows import dict_row

    return dict_row


def clear_thread(database_url: str, thread_id: str) -> None:
    conn = Connection.connect(_dsn(database_url), autocommit=True)
    try:
        with conn.cursor() as cur:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                cur.execute(f"DELETE FROM {table} WHERE thread_id = %s", (thread_id,))
    except Exception:
        pass
    finally:
        conn.close()


def summarise(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {"value": str(values)[:2000]}

    out: dict[str, Any] = {}
    for key, value in values.items():
        if value == RESET:
            out[key] = {"cleared": True}
        elif key in BULKY and isinstance(value, list):
            out[key] = {"count": len(value)}
        elif key == "pending" and isinstance(value, list):
            out[key] = {"remaining": len(value), "next": value[:PREVIEW_ITEMS]}
        else:
            out[key] = value
    return out


def _id(config: Any) -> str | None:
    return ((config or {}).get("configurable") or {}).get("checkpoint_id")


def _open(database_url: str) -> tuple[Any, Connection]:
    from .build import build_graph, hollow_deps

    conn, saver = checkpoint_saver(database_url)
    return build_graph(hollow_deps(), checkpointer=saver), conn


def _step(snapshot: Any, full: bool, wrote: list[str]) -> dict[str, Any]:
    metadata = snapshot.metadata or {}
    return {
        "checkpoint_id": _id(snapshot.config),
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
    app, conn = _open(database_url)
    try:
        snapshots = list(app.get_state_history({"configurable": {"thread_id": thread_id}}, limit=limit))
    finally:
        conn.close()

    queued = {_id(snapshot.config): list(snapshot.next) for snapshot in snapshots}
    return [_step(snapshot, full, queued.get(_id(snapshot.parent_config), [])) for snapshot in reversed(snapshots)]


def read_state(database_url: str, thread_id: str, checkpoint_id: str | None = None) -> dict[str, Any] | None:
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
    app, conn = _open(database_url)
    try:
        config = _config(thread_id, checkpoint_id)
        if as_node is None:
            wrote = _wrote(app, app.get_state(config))
            as_node = wrote[0] if wrote else None
        written = app.update_state(config, values, as_node=as_node)
    finally:
        conn.close()

    return ((written or {}).get("configurable") or {}).get("checkpoint_id")


def _config(thread_id: str, checkpoint_id: str | None) -> dict[str, Any]:
    configurable: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": ""}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}
