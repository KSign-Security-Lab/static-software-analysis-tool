"""Creating the schema, and the one extension it needs.

`create_all`, not Alembic. That is a considered trade for a laptop-scale tool:
there is no data worth migrating and no deployed environment to migrate it in.
It is also the first thing to revisit -- the moment a column changes, every
database needs a manual drop and recreate, and that stops being acceptable as
soon as anyone other than the author has one.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from .models import Base


def create_all(bound: Engine) -> None:
    """Build the schema, extension first.

    `vector` has to exist before the `vectors` table is declared against it, and
    `CREATE EXTENSION IF NOT EXISTS` needs rights the application user may not
    have -- so a database that already has it installed works, and one that does
    not fails here with a clear message rather than at the first embedding.
    """
    with bound.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bound)


def drop_all(bound: Engine) -> None:
    """Tear it down. Tests, and the manual recreate that no-Alembic implies."""
    Base.metadata.drop_all(bound)


#: Whether this process has already built the schema. Not a cache of whether the
#: tables exist -- a second process may create them -- only of whether *we* have
#: asked, which is enough to keep the cost at one statement per process.
_ensured = False


def ensure(bound: Engine | None = None) -> None:
    """Create anything missing, once per process.

    `create_all` was called from the test fixtures and nowhere else, so every
    table this package has ever added arrived in a database that tests had built
    and production had not. That worked for as long as nobody added a table: the
    old ones were created by whoever first ran the suite against a shared
    database. Adding one broke a real run and no test, which is the worst shape
    a gap can have.

    Idempotent and cheap -- `CREATE TABLE IF NOT EXISTS` against a schema that
    already matches is a catalogue read. Called from the places a run actually
    starts rather than at import, so importing the package still costs nothing.
    """
    global _ensured
    if _ensured:
        return
    from .session import engine

    create_all(bound if bound is not None else engine())
    _ensured = True
