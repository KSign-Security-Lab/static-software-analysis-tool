"""Shared fixtures for the agent test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

#: Multi-file C with a real call graph, and every function labelled VULNERABLE
#: or SAFE in its own header comment.
#:
#: This package owns its test data. An earlier version reached into
#: ``packages/ssat/tests/fixtures/f2a`` -- convenient, but it coupled this
#: suite to another package's private fixtures and made an unrelated analysis
#: line look like part of this one.
SAMPLE_TREE = Path(__file__).resolve().parent / "fixtures" / "sample"


@pytest.fixture
def fixture_root() -> Path:
    if not SAMPLE_TREE.is_dir():
        pytest.skip(f"sample tree missing: {SAMPLE_TREE}")
    return SAMPLE_TREE


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
