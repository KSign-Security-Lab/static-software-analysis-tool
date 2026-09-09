"""CPG generation: Joern's JARs in a JVM inside this process.

There were two engines behind one interface, `jpype` and `docker`. The second
ran `docker exec` into a Joern container, which meant a second Joern install to
keep in step with the first -- and they had drifted, 4.0.377 locally against the
Dockerfile's 4.0.361. It is gone, with the container, the endpoint that reached
it and the test that measured the skew.

What that costs, stated plainly: a host with no local Joern can no longer
generate a CPG at all. Set ``JOERN_HOME`` to a `joern-cli` install (it defaults
to `/usr/bin/joern/joern-cli`) and have a JDK on the path -- see
:mod:`ssat.cpg.embedded`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


def count_methods(graphson: Dict[str, Any]) -> int:
    """Count METHOD vertices in a GraphSON document.

    The previous counter looked for a top-level ``method`` key, which
    joern-export's GraphSON does not contain, so it always returned 0. The web
    API carried its own corrected copy; this is now the only implementation.
    """
    value = graphson.get("@value") if isinstance(graphson, dict) else None
    vertices = value.get("vertices", []) if isinstance(value, dict) else []
    return sum(1 for v in vertices if isinstance(v, dict) and v.get("label") == "METHOD")


@dataclass(frozen=True)
class CpgResult:
    """A generated CPG plus how it was produced."""

    graphson: Dict[str, Any]
    method_count: int
    backend: str

    @property
    def document(self) -> Dict[str, Any]:
        """The ``{"export": ...}`` shape the template pipeline consumes."""
        return {"export": self.graphson}


class EmbeddedBackend:
    """In-process Joern via JPype.

    Still a class rather than two functions: `name` and `is_available` are what
    `/health` reports, and the JVM being warm after the first call is the reason
    this is the only engine now.
    """

    name = "jpype"

    def is_available(self) -> bool:
        from . import embedded

        return embedded.is_available()

    def generate(self, source: str, *, filename: str = "main.c", representation: str = "all") -> CpgResult:
        from . import embedded

        graphson = embedded.generate_cpg(source, filename=filename, representation=representation)
        return CpgResult(graphson, count_methods(graphson), self.name)

    def generate_file(self, source_file: Path, *, representation: str = "all") -> CpgResult:
        """Generate from a file on disk, preserving its name."""
        return self.generate(
            source_file.read_text(encoding="utf-8", errors="replace"),
            filename=source_file.name,
            representation=representation,
        )


def generate_cpg(source: str, *, filename: str = "main.c", representation: str = "all") -> CpgResult:
    """Generate a CPG from source text."""
    return EmbeddedBackend().generate(source, filename=filename, representation=representation)
