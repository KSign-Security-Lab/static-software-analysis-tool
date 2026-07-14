"""Public entry point for F2-A: run the pipeline on a CPG and emit artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List, Optional

from .graph import CPGModel
from .kb import KnowledgeBase
from .models import F2AResult
from .pipeline import F2AAnalyzer


def run_f2a(
    cpg_json: Any,
    kb: Optional[KnowledgeBase] = None,
    source_cpg: str = "",
) -> F2AResult:
    """Run the 7-step F2-A pipeline over one in-memory CPG (GraphSON) document."""
    model = CPGModel(cpg_json)
    analyzer = F2AAnalyzer(model, kb=kb)
    return analyzer.analyze(source_cpg=source_cpg)


def run_f2a_file(
    cpg_path: str | Path,
    kb: Optional[KnowledgeBase] = None,
) -> F2AResult:
    """Load a CPG JSON file and run F2-A over it."""
    path = Path(cpg_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return run_f2a(data, kb=kb, source_cpg=str(path))


# Files written by :func:`write_artifacts`, mirroring the design's output set (§15).
_ARTIFACT_FILES: dict[str, Callable[[F2AResult], List[Any]]] = {
    "handler_map.json": lambda r: [m.model_dump() for m in r.handler_maps],
    "field_binding_map.json": lambda r: [b.model_dump() for b in r.field_bindings],
    "ocpp_flow_candidates.json": lambda r: [c.model_dump() for c in r.flow_candidates],
    "dangerous_sink_mapping.json": lambda r: [s.model_dump() for s in r.sink_mappings],
    "expected_check_matching_results.json": lambda r: [
        m.model_dump() for m in r.expected_check_matchings
    ],
    "missing_check_candidates.json": lambda r: [
        m.model_dump() for m in r.missing_check_candidate_sets
    ],
    "ocpp_evidence_packages.json": lambda r: [
        p.model_dump() for p in r.evidence_packages
    ],
    "ocpp_native_candidate_fragments.json": lambda r: [
        f.model_dump() for f in r.candidate_fragments
    ],
}


def write_artifacts(result: F2AResult, output_dir: str | Path) -> list[Path]:
    """Write the individual F2-A artifact files plus a combined report."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for filename, extractor in _ARTIFACT_FILES.items():
        payload = extractor(result)
        target = out / filename
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        written.append(target)

    combined = out / "f2a_result.json"
    combined.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    written.append(combined)
    return written
