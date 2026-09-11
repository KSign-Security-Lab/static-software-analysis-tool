from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import AgentConfig

# A round now runs many chunks at once, each doing its own small reads between model
# calls. The default pool (5 + 10) is below that, and a starved checkout blocks for
# 30s before raising, which reads as the model being slow.
POOL_SIZE = 32
MAX_OVERFLOW = 32

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def engine(config: AgentConfig | None = None) -> Engine:
    global _engine, _factory
    if _engine is None:
        url = (config or AgentConfig()).database_url
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_recycle=1800,
            future=True,
        )
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_factory(config: AgentConfig | None = None) -> sessionmaker[Session]:
    engine(config)
    assert _factory is not None
    return _factory


@contextmanager
def session_scope(config: AgentConfig | None = None) -> Iterator[Session]:
    with session_factory(config)() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def reset(new_engine: Engine | None = None) -> None:
    global _engine, _factory
    if _engine is not None and new_engine is not _engine:
        _engine.dispose()
    _engine = new_engine
    _factory = sessionmaker(bind=new_engine, expire_on_commit=False) if new_engine else None
