"""One engine, one session factory, and the rule about who opens a session.

Sync, not async, and that is a decision rather than an oversight: the agent
package is synchronous throughout -- tree-sitter, the LLM client, the graph
nodes -- so an async session would colour every call in `steps.py`, `tools.py`
and the CLI to buy concurrency at a layer that has none. FastAPI runs sync
endpoints in a threadpool, which is what it already does for this workload.

The engine is process-wide and lazy. Import time is the wrong moment to open a
socket: the CLI imports this to print help, and the tests import it to build a
schema against a database whose URL they set first.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import AgentConfig

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def engine(config: AgentConfig | None = None) -> Engine:
    """The process's engine, built on first use."""
    global _engine, _factory
    if _engine is None:
        url = (config or AgentConfig()).database_url
        # `pool_pre_ping` because the common local setup is Postgres in Docker,
        # and a container restart otherwise hands out dead connections until
        # something times out.
        _engine = create_engine(url, pool_pre_ping=True, future=True)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_factory(config: AgentConfig | None = None) -> sessionmaker[Session]:
    engine(config)
    assert _factory is not None
    return _factory


@contextmanager
def session_scope(config: AgentConfig | None = None) -> Iterator[Session]:
    """A session that commits on success and rolls back on anything else.

    The unit of work is the caller's, not the store's: a store method that
    committed on its own would make "index this tree" a few thousand
    transactions and leave a half-indexed run behind when one of them failed.
    """
    with session_factory(config)() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def reset(new_engine: Engine | None = None) -> None:
    """Point the process at a different database, or forget the current one.

    For tests, which build a schema per session against a throwaway database.
    Nothing in the application calls this.
    """
    global _engine, _factory
    if _engine is not None and new_engine is not _engine:
        _engine.dispose()
    _engine = new_engine
    _factory = sessionmaker(bind=new_engine, expire_on_commit=False) if new_engine else None
