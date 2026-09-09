from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


def count_methods(graphson: Dict[str, Any]) -> int:
    value = graphson.get("@value") if isinstance(graphson, dict) else None
    vertices = value.get("vertices", []) if isinstance(value, dict) else []
    return sum(1 for v in vertices if isinstance(v, dict) and v.get("label") == "METHOD")


@dataclass(frozen=True)
class CpgResult:
    graphson: Dict[str, Any]
    method_count: int
    backend: str

    @property
    def document(self) -> Dict[str, Any]:
        return {"export": self.graphson}


class EmbeddedBackend:
    name = "jpype"

    def is_available(self) -> bool:
        from . import embedded

        return embedded.is_available()

    def generate(self, source: str, *, filename: str = "main.c", representation: str = "all") -> CpgResult:
        from . import embedded

        graphson = embedded.generate_cpg(source, filename=filename, representation=representation)
        return CpgResult(graphson, count_methods(graphson), self.name)

    def generate_file(self, source_file: Path, *, representation: str = "all") -> CpgResult:
        return self.generate(
            source_file.read_text(encoding="utf-8", errors="replace"),
            filename=source_file.name,
            representation=representation,
        )


def generate_cpg(source: str, *, filename: str = "main.c", representation: str = "all") -> CpgResult:
    return EmbeddedBackend().generate(source, filename=filename, representation=representation)
