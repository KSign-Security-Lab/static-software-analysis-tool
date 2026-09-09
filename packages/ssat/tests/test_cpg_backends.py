"""CPG generation, in the process that asks for it.

There were two engines here, `jpype` and `docker`, and most of this file
existed to prove they agreed. The container is gone, so what is left is the one
engine, the pure functions around it, and the batch driver that now runs
through it.

The tests that need Joern skip when there are no JARs to load. The pure ones
always run.
"""

from __future__ import annotations

import json

import pytest

from legacy_chain import all_fixtures

from ssat.cpg.backends import EmbeddedBackend, count_methods

SOURCE = """\
#include <string.h>

void store(const char *src, unsigned len) {
    char buf[64];
    memcpy(buf, src, len);
}

int main(void) {
    store("x", 1);
    return 0;
}
"""


def _graph(doc):
    return doc.get("@value", {})


def test_count_methods_counts_method_vertices():
    """The old counter looked for a top-level 'method' key GraphSON lacks.

    It therefore returned 0 for every CPG ever generated, which is why the web
    API grew its own corrected copy.
    """
    fixture = next(p for p in all_fixtures() if p.name == "update_firmware.c.json")
    graphson = json.loads(fixture.read_text(encoding="utf-8"))

    vertices = _graph(graphson).get("vertices", [])
    expected = sum(1 for v in vertices if v.get("label") == "METHOD")

    assert expected > 0, "fixture should contain METHOD vertices"
    assert count_methods(graphson) == expected


def test_count_methods_tolerates_junk():
    assert count_methods({}) == 0
    assert count_methods({"@value": {}}) == 0
    assert count_methods({"@value": {"vertices": ["not-a-dict"]}}) == 0


def test_cpg_result_exposes_the_pipeline_shape():
    from ssat.cpg.backends import CpgResult

    result = CpgResult({"@value": {"vertices": []}}, 0, "jpype")
    assert result.document == {"export": result.graphson}


def test_the_engine_produces_valid_graphson():
    backend = EmbeddedBackend()
    if not backend.is_available():
        pytest.skip("no Joern JARs; set JOERN_HOME")

    result = backend.generate(SOURCE, filename="main.c")

    assert result.backend == "jpype"
    assert result.method_count >= 2, "expected at least store() and main()"
    graph = _graph(result.graphson)
    assert graph.get("vertices"), "no vertices in GraphSON"
    assert graph.get("edges"), "no edges in GraphSON"


# -- the batch driver ---------------------------------------------------------


def test_the_batch_driver_writes_one_cpg_per_file(tmp_path):
    """It used to drive `docker exec` per file. It drives a JVM per worker now.

    The `spawn` start method is what makes that safe: forking a process that
    has already started a JVM gives the child one it cannot use, and pytest may
    well have started one in an earlier test.
    """
    from ssat.cpg.generator import batch_generate_cpg

    if not EmbeddedBackend().is_available():
        pytest.skip("no Joern JARs; set JOERN_HOME")

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "one.c").write_text(SOURCE, encoding="utf-8")
    (source_dir / "two.c").write_text(SOURCE.replace("store", "keep"), encoding="utf-8")
    out = tmp_path / "out"

    results = batch_generate_cpg(
        files=sorted(source_dir.glob("*.c")),
        input_root=source_dir,
        output_root=out,
        workers=2,
    )

    assert [r["success"] for r in results] == [True, True], results
    written = sorted(p.name for p in out.glob("*.json"))
    assert written == ["one.c.json", "two.c.json"]
    for path in out.glob("*.json"):
        assert count_methods(json.loads(path.read_text(encoding="utf-8"))) >= 2
