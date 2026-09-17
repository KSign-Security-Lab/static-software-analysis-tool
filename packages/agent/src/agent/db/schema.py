from __future__ import annotations

from sqlalchemy import Engine, text

from .models import Base


def create_all(bound: Engine) -> None:
    with bound.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bound)


def drop_all(bound: Engine) -> None:
    Base.metadata.drop_all(bound)


_ensured = False


def ensure(bound: Engine | None = None) -> None:
    global _ensured
    if _ensured:
        return
    from .session import engine

    create_all(bound if bound is not None else engine())
    _ensured = True
