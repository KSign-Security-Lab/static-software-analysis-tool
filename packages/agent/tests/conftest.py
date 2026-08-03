"""Shared fixtures for the agent test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

#: Real C source with known call chains, reused rather than duplicated. These
#: files belong to the ssat suite; the agent only reads them.
F2A_FIXTURES = Path(__file__).resolve().parents[2] / "ssat" / "tests" / "fixtures" / "f2a"


@pytest.fixture
def fixture_root() -> Path:
    if not F2A_FIXTURES.is_dir():
        pytest.skip(f"fixture corpus missing: {F2A_FIXTURES}")
    return F2A_FIXTURES


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small multi-file C tree with a known call graph and a known cycle."""
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
