"""The two CPG backends must be interchangeable.

``jpype`` and ``docker`` run the same Joern, one in-process and one in a
container. Anything that reads a CPG must not care which produced it, so the
GraphSON they return has to agree structurally.

Both backends need a real Joern install, so the equivalence test skips when the
environment cannot run them. The pure-function tests always run.
"""

from __future__ import annotations

import json

import pytest

from legacy_chain import all_fixtures

from ssat.cpg.backends import (
    BACKEND_NAMES,
    CpgBackend,
    DockerBackend,
    EmbeddedBackend,
    count_methods,
    get_backend,
)

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


def test_both_backends_are_registered():
    assert set(BACKEND_NAMES) == {"jpype", "docker"}
    for name in BACKEND_NAMES:
        backend = get_backend(name)
        assert isinstance(backend, CpgBackend)
        assert backend.name == name


def test_unknown_backend_names_the_alternatives():
    with pytest.raises(ValueError, match="jpype"):
        get_backend("nope")


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


@pytest.mark.parametrize("backend_name", BACKEND_NAMES)
def test_backend_produces_valid_graphson(backend_name):
    backend = get_backend(backend_name)
    if not backend.is_available():
        pytest.skip(f"{backend_name} backend unavailable in this environment")

    result = backend.generate(SOURCE, filename="main.c")

    assert result.backend == backend_name
    assert result.method_count >= 2, "expected at least store() and main()"
    graph = _graph(result.graphson)
    assert graph.get("vertices"), "no vertices in GraphSON"
    assert graph.get("edges"), "no edges in GraphSON"


def test_backends_agree():
    """Same source through both engines yields an equivalent graph.

    Asserted at the level that must hold whatever Joern version each side runs:
    the same methods, and the same *kinds* of vertex and edge present. Exact
    counts are deliberately not compared -- the container pins Joern 4.0.361
    (see ``Dockerfile``) while a local install may be newer, and minor releases
    change how many METHOD_PARAMETER_* and REACHING_DEF elements they emit.
    Use :func:`test_report_backend_skew` to see the current difference.
    """
    embedded, docker = EmbeddedBackend(), DockerBackend()
    if not (embedded.is_available() and docker.is_available()):
        pytest.skip("need both a local Joern install and a running Joern container")

    embedded_result = embedded.generate(SOURCE, filename="main.c")
    docker_result = docker.generate(SOURCE, filename="main.c")

    assert embedded_result.method_count == docker_result.method_count

    def labels(result):
        graph = _graph(result.graphson)
        return (
            {v.get("label") for v in graph.get("vertices", [])},
            {e.get("label") for e in graph.get("edges", [])},
        )

    assert labels(embedded_result) == labels(docker_result)

    def method_names(result):
        graph = _graph(result.graphson)
        names = set()
        for vertex in graph.get("vertices", []):
            if vertex.get("label") != "METHOD":
                continue
            prop = vertex.get("properties", {}).get("NAME", {})
            inner = prop.get("@value", {})
            values = inner.get("@value", []) if isinstance(inner, dict) else []
            names.update(str(v) for v in values)
        return names

    assert method_names(embedded_result) == method_names(docker_result)


def test_report_backend_skew():
    """Diagnostic: print how far the two engines differ, never fails.

    A non-empty report means the local Joern and the container's Joern are
    different versions. Align them by matching ``JOERN_VERSION`` in the
    Dockerfile to the local install, or accept the skew knowingly.
    """
    embedded, docker = EmbeddedBackend(), DockerBackend()
    if not (embedded.is_available() and docker.is_available()):
        pytest.skip("need both a local Joern install and a running Joern container")

    from collections import Counter

    def counts(result):
        graph = _graph(result.graphson)
        return (
            Counter(v.get("label") for v in graph.get("vertices", [])),
            Counter(e.get("label") for e in graph.get("edges", [])),
        )

    embedded_vertices, embedded_edges = counts(embedded.generate(SOURCE, filename="main.c"))
    docker_vertices, docker_edges = counts(docker.generate(SOURCE, filename="main.c"))

    differences = [
        f"  {kind:<8} {label:<22} jpype={a.get(label, 0):<5} docker={b.get(label, 0)}"
        for kind, a, b in (
            ("vertex", embedded_vertices, docker_vertices),
            ("edge", embedded_edges, docker_edges),
        )
        for label in sorted(set(a) | set(b))
        if a.get(label, 0) != b.get(label, 0)
    ]
    if differences:
        print("\nbackend skew (likely differing Joern versions):")
        print("\n".join(differences))
