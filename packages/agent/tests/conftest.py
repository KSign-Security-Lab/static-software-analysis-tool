from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from agent.config import ENV_DATABASE_URL
from agent.db import Base, schema
from agent.index import ChunkStore
from agent.db import session as db_session

SAMPLE_TREE = Path(__file__).resolve().parent / "fixtures" / "sample"


TEST_DATABASE_URL = os.getenv("AGENT_TEST_DATABASE_URL", "postgresql+psycopg://ssat:ssat@localhost:4402/ssat_test")


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    name = TEST_DATABASE_URL.rsplit("/", 1)[1]
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
        with admin.connect() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}):
                conn.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
    except OperationalError as err:
        pytest.skip(f"no Postgres for the agent test suite: {err}")

    os.environ[ENV_DATABASE_URL] = TEST_DATABASE_URL
    bound = create_engine(TEST_DATABASE_URL, future=True)
    db_session.reset(bound)
    schema.drop_all(bound)
    schema.create_all(bound)
    yield
    db_session.reset(None)


@pytest.fixture(autouse=True)
def _isolated_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_PROMPTS_FILE", str(tmp_path / "artifacts" / "prompts.json"))
    ours = [f'"{table.name}"' for table in Base.metadata.sorted_tables]
    with db_session.session_scope() as session:
        theirs = list(
            session.scalars(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                    " AND tablename LIKE 'checkpoint%'"
                )
            )
        )
        tables = ", ".join(ours + [f'"{name}"' for name in theirs])
        session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def read_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def fixture_root() -> Path:
    if not SAMPLE_TREE.is_dir():
        pytest.skip(f"sample tree missing: {SAMPLE_TREE}")
    return SAMPLE_TREE


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "util.h").write_text(
        "#ifndef UTIL_H\n#define UTIL_H\ntypedef struct { char *location; } Request;\nvoid log_msg(const char *m);\n#endif\n",
        encoding="utf-8",
    )
    (tmp_path / "util.c").write_text(
        '#include "util.h"\n#include <stdio.h>\nvoid log_msg(const char *m) { printf("%s", m); }\n',
        encoding="utf-8",
    )
    (tmp_path / "app.c").write_text(
        '#include "util.h"\n'
        "#include <stdlib.h>\n"
        "static void inner(Request *r) { log_msg(r->location); system(r->location); }\n"
        "static void outer(Request *r) { inner(r); }\n"
        "void entry(Request *r) { outer(r); }\n"
        "static void ping(int n) { if (n) pong(n - 1); }\n"
        "static void pong(int n) { if (n) ping(n - 1); }\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def tree_files(tree: Path) -> dict[str, str]:
    return read_tree(tree)


@pytest.fixture
def fixture_files(fixture_root: Path) -> dict[str, str]:
    return read_tree(fixture_root)


@pytest.fixture
def store() -> Iterator[ChunkStore]:
    from agent.runs import new_run

    opened = new_run().store()
    try:
        yield opened
    finally:
        opened.close()
