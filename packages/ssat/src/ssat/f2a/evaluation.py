"""F2-A handler-resolution evaluation harness.

Runs the resolver over a corpus (a directory of pre-generated CPG GraphSON
``.json`` files, or a directory of C/C++ sources compiled to CPGs on the fly) and
produces a deterministic JSON report plus a human-readable Markdown summary.

This is *evaluation tooling*, not an analysis backend: it never resolves handlers
itself, adds no dispatch support, and does not change the calculus. It classifies
each unresolved / ambiguous outcome into a fixed taxonomy, and — crucially — does
not claim certainty when the required information is absent (every classification
carries a confidence and its supporting observations).

Determinism: the ``metrics`` and ``actions`` sections are a pure function of the
corpus + calculus config. The ``run`` metadata (timestamp, tool commit) and the
``performance`` section (wall-clock runtime) are intentionally NOT deterministic
and are excluded from equality checks.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .graph import CPGModel
from .kb import KnowledgeBase, default_knowledge_base
from .pipeline import F2AAnalyzer, cpg_id
from .resolution import CalculusConfig

# ---------------------------------------------------------------------------
# Fixed classification taxonomy (locked before running)
# ---------------------------------------------------------------------------
#
# UNRESOLVED
# ├── ANALYSIS_SCOPE
# │   ├── EXTERNAL_DEFINITION
# │   ├── CROSS_TU_REGISTRATION
# │   └── MISSING_CPG_RELATION
# ├── POTENTIALLY_SUPPORTABLE
# │   ├── INDIRECT_CALL
# │   ├── ALIAS_OR_POINTS_TO
# │   ├── VARIABLE_INDEX_CORRELATION
# │   └── PREPROCESSOR_OR_MACRO
# ├── POLICY
# │   ├── LOW_CONFIDENCE
# │   └── COMPETING_CANDIDATES
# └── UNKNOWN

TIER_ANALYSIS_SCOPE = "ANALYSIS_SCOPE"
TIER_POTENTIALLY_SUPPORTABLE = "POTENTIALLY_SUPPORTABLE"
TIER_POLICY = "POLICY"
TIER_UNKNOWN = "UNKNOWN"


@dataclass
class Classification:
    tier: str
    backend_category: Optional[str]
    classification_confidence: str  # HIGH | MEDIUM | LOW
    supporting_observations: List[str] = field(default_factory=list)


def classify_outcome(hr: Any, action_referenced: bool) -> Optional[Classification]:
    """Classify a non-RESOLVED outcome into the taxonomy. Returns None for
    RESOLVED. Confidence reflects how directly the structured reason implies the
    leaf; alternatives are listed rather than silently discarded."""
    if hr.status == "AMBIGUOUS":
        return Classification(
            TIER_POLICY,
            "COMPETING_CANDIDATES",
            "HIGH",
            [f"{len(hr.candidates)} competing candidates within the ambiguity margin"],
        )
    if hr.status != "UNRESOLVED":
        return None

    u = hr.unresolved
    reason = u.reason if u is not None else "NO_EVIDENCE"
    obs: List[str] = []
    if u is not None and u.dispatch_site is not None:
        obs.append(f"dispatch site: {u.dispatch_site.code!r} @ {u.dispatch_site.file}:{u.dispatch_site.line}")
    if u is not None and u.secondary:
        obs.append(f"secondary reason: {u.secondary}")

    if reason == "LOW_CONFIDENCE":
        return Classification(TIER_POLICY, "LOW_CONFIDENCE", "HIGH", ["top candidate below MIN_CONFIDENCE"] + obs)
    if reason == "EXTERNAL_DEFINITION":
        return Classification(
            TIER_ANALYSIS_SCOPE,
            "EXTERNAL_DEFINITION",
            "HIGH",
            ["handler defined outside the analyzed translation unit"] + obs,
        )
    if reason == "UNRESOLVED_INDIRECT_CALL":
        return Classification(
            TIER_POTENTIALLY_SUPPORTABLE,
            "INDIRECT_CALL",
            "MEDIUM",
            ["indirect/pointer-call dispatch site present", "alternative: cross-TU external definition"] + obs,
        )
    if reason == "UNSUPPORTED_REGISTRAR_CALL":
        return Classification(
            TIER_POTENTIALLY_SUPPORTABLE,
            "INDIRECT_CALL",
            "LOW",
            ["registrar call target unresolved", "alternatives: PREPROCESSOR_OR_MACRO, ALIAS_OR_POINTS_TO"] + obs,
        )
    if reason == "REGISTRAR_STORE_NOT_REACHED":
        return Classification(
            TIER_POTENTIALLY_SUPPORTABLE,
            "VARIABLE_INDEX_CORRELATION",
            "LOW",
            [
                "registrar resolved but terminal store not reached within depth",
                "alternatives: deeper traversal, ALIAS_OR_POINTS_TO",
            ]
            + obs,
        )
    if reason == "REGISTRAR_SEARCH_THEN_WRITE":
        return Classification(
            TIER_POTENTIALLY_SUPPORTABLE,
            "SEARCH_THEN_WRITE_REGISTRAR",
            "LOW",
            [
                "registrar resolved but selects the slot at runtime "
                "(loop + action predicate) and stores only the callback",
                "escalation: loop/predicate reasoning + symbolic index + alias->slot",
            ]
            + obs,
        )
    if reason == "NO_EVIDENCE":
        if action_referenced:
            return Classification(
                TIER_ANALYSIS_SCOPE,
                "CROSS_TU_REGISTRATION",
                "MEDIUM",
                ["action id referenced in this TU but no registration/dispatch found"] + obs,
            )
        return Classification(
            TIER_UNKNOWN, None, "LOW", ["action id not referenced in this TU; cannot attribute a cause"] + obs
        )
    return Classification(TIER_UNKNOWN, None, "LOW", [f"unmapped reason {reason}"] + obs)


# ---------------------------------------------------------------------------
# Corpus evaluation
# ---------------------------------------------------------------------------


def _action_referenced(cpg: CPGModel, kb: KnowledgeBase, action: str) -> bool:
    """Cheap observation: does the action id appear anywhere in this CPG (as a
    string/enum symbol or numeric id)? Used only to distinguish cross-TU
    registration from an action that is simply absent — never to resolve."""
    prof = kb.actions.get(action)
    up = "".join(
        "_" + c if c.isupper() and i and not action[i - 1].isupper() else c.upper() for i, c in enumerate(action)
    )
    tokens = {action.upper(), up}
    for s in prof.action_symbols if prof else []:
        tokens.add(s.upper())
    numeric = {str(n) for n in (prof.numeric_ids if prof else [])}
    for v in cpg.vertices:
        lbl = v.get("label")
        if lbl not in ("LITERAL", "IDENTIFIER", "CALL", "FIELD_IDENTIFIER", "JUMP_TARGET"):
            continue
        vid = cpg_id(v)
        code_u = str(cpg.code(vid) or "").upper()
        if any(t and t in code_u for t in tokens):
            return True
        if lbl == "LITERAL" and str(cpg.code(vid) or "").strip() in numeric:
            return True
    return False


def _stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None, "median": None}
    return {
        "count": len(values),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(statistics.fmean(values), 6),
        "median": round(statistics.median(values), 6),
    }


def _evaluate_one(cpg: CPGModel, corpus_file: str, kb: KnowledgeBase, cfg: CalculusConfig) -> List[Dict[str, Any]]:
    """Per-action records for one CPG."""
    analyzer = F2AAnalyzer(cpg, kb=kb, calculus=cfg)
    result = analyzer.analyze()
    by_action = {hr.action: hr for hr in result.handler_resolutions}
    selection = getattr(analyzer, "_selection", {})

    records: List[Dict[str, Any]] = []
    for action in sorted(by_action):
        hr = by_action[action]
        sel = selection.get(action)
        cands = sel.candidates if sel is not None else []
        evidence_count = sum(len(c.evidence) for c in cands)

        top = sel.chosen if (sel is not None and sel.chosen is not None) else (cands[0] if cands else None)
        top_conf = top.confidence if top is not None else None
        runner = cands[1].confidence if len(cands) > 1 else None
        margin = round(top.confidence - runner, 6) if (top is not None and runner is not None) else None
        lift = None
        if top is not None and top.evidence:
            best_ev = max((e.score for e in top.evidence), default=0.0)
            if best_ev > 0:
                lift = round(top.confidence - best_ev, 6)

        classification = None
        if hr.status != "RESOLVED":
            referenced = _action_referenced(cpg, kb, action)
            c = classify_outcome(hr, referenced)
            classification = asdict(c) if c is not None else None

        records.append(
            {
                "corpus_file": corpus_file,
                "action": action,
                "status": hr.status,
                "chosen_function": hr.chosen.function if hr.chosen is not None else None,
                "unresolved_reason": hr.unresolved.reason if hr.unresolved is not None else None,
                "candidate_count": len(cands),
                "evidence_count": evidence_count,
                "evidence_kinds": sorted({k for c in hr.candidates for k in c.evidence_kinds}),
                "top_confidence": top_conf,
                "runner_up_confidence": runner,
                "margin": margin,
                "corroboration_lift": lift,
                "classification": classification,
            }
        )
    return records


def _aggregate(records: List[Dict[str, Any]], n_cpgs: int, cfg: CalculusConfig) -> Dict[str, Any]:
    outcomes: Dict[str, int] = {"RESOLVED": 0, "AMBIGUOUS": 0, "UNRESOLVED": 0}
    reason_hist: Dict[str, int] = {}
    tier_hist: Dict[str, int] = {}
    backend_hist: Dict[str, Dict[str, int]] = {}  # backend -> {confidence: count}
    resolved_conf: List[float] = []
    margins: List[float] = []
    lifts: List[float] = []
    within_margin = 0

    for r in records:
        outcomes[r["status"]] = outcomes.get(r["status"], 0) + 1
        if r["status"] == "RESOLVED" and r["top_confidence"] is not None:
            resolved_conf.append(r["top_confidence"])
            if r["corroboration_lift"] is not None:
                lifts.append(r["corroboration_lift"])
        if r["margin"] is not None:
            margins.append(r["margin"])
            if r["margin"] < cfg.ambiguity_margin:
                within_margin += 1
        if r["status"] == "UNRESOLVED":
            reason_hist[r["unresolved_reason"] or "NONE"] = reason_hist.get(r["unresolved_reason"] or "NONE", 0) + 1
        if r["status"] != "RESOLVED":
            cl = r["classification"]
            if cl is not None:
                tier_hist[cl["tier"]] = tier_hist.get(cl["tier"], 0) + 1
                b = cl["backend_category"] or "NONE"
                backend_hist.setdefault(b, {})
                backend_hist[b][cl["classification_confidence"]] = (
                    backend_hist[b].get(cl["classification_confidence"], 0) + 1
                )

    return {
        # 1. resolution outcome counts
        "outcome_counts": outcomes,
        # 2. unresolved-reason histogram with analysis-scope separation (tier_histogram)
        "unresolved_reason_histogram": dict(sorted(reason_hist.items())),
        "tier_histogram": dict(sorted(tier_hist.items())),
        # 3. likely backend required
        "backend_histogram": {k: dict(sorted(v.items())) for k, v in sorted(backend_hist.items())},
        # 4. confidence / corroboration-lift / ambiguity-margin distributions
        "resolved_confidence": _stats(resolved_conf),
        "corroboration_lift": _stats(lifts),
        "margin": _stats(margins),
        "within_ambiguity_margin": within_margin,
        # 5. volume
        "totals": {
            "cpgs": n_cpgs,
            "actions": len(records),
            "resolved": outcomes["RESOLVED"],
            "ambiguous": outcomes["AMBIGUOUS"],
            "unresolved": outcomes["UNRESOLVED"],
        },
        "evidence_volume": _stats([float(r["evidence_count"]) for r in records]),
        "candidate_volume": _stats([float(r["candidate_count"]) for r in records]),
    }


def _tool_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def evaluate_cpgs(
    cpgs: List[Tuple[str, CPGModel]],
    corpus_id: str,
    kb: Optional[KnowledgeBase] = None,
    cfg: Optional[CalculusConfig] = None,
    cpg_config: str = "pre-generated",
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Core evaluator over an ordered list of ``(name, CPGModel)`` pairs."""
    kb = kb or default_knowledge_base()
    cfg = cfg or CalculusConfig()

    records: List[Dict[str, Any]] = []
    per_cpg_runtime: Dict[str, float] = {}
    t_all = time.perf_counter()
    for name, cpg in cpgs:
        t0 = time.perf_counter()
        records.extend(_evaluate_one(cpg, name, kb, cfg))
        per_cpg_runtime[name] = round(time.perf_counter() - t0, 6)
    total_runtime = round(time.perf_counter() - t_all, 6)

    records.sort(key=lambda r: (r["corpus_file"], r["action"]))
    return {
        "run": {
            "tool_commit": _tool_commit(),
            "calculus_config": asdict(cfg),
            "corpus_id": corpus_id,
            "cpg_generation_config": cpg_config,
            "timestamp": timestamp,  # metadata only; excluded from determinism checks
        },
        "metrics": _aggregate(records, len(cpgs), cfg),
        "actions": records,
        "performance": {
            "total_runtime_s": total_runtime,
            "per_cpg_runtime_s": per_cpg_runtime,
        },
    }


def evaluate_cpg_dir(cpg_dir: Path, corpus_id: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
    """Evaluate a directory of pre-generated CPG GraphSON ``.json`` files."""
    cpg_dir = Path(cpg_dir)
    files = sorted(cpg_dir.glob("*.json"))
    cpgs = [(f.name, CPGModel(json.loads(f.read_text()))) for f in files]
    return evaluate_cpgs(cpgs, corpus_id or cpg_dir.name, cpg_config="pre-generated", **kw)


def evaluate_source_dir(src_dir: Path, corpus_id: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
    """Evaluate a directory of C/C++ sources, generating a CPG per file via the
    embedded Joern frontend. Imported lazily so CPG-mode needs no JVM."""
    from .. import cpg as _cpgpkg  # noqa: F401  (ensure package import path)
    from ssat.cpg.embedded import generate_cpg, joern_home

    src_dir = Path(src_dir)
    files = sorted(p for p in src_dir.rglob("*") if p.suffix in (".c", ".cc", ".cpp", ".cxx"))
    cpgs = [(str(p.relative_to(src_dir)), CPGModel(generate_cpg(p.read_text(), p.name))) for p in files]
    return evaluate_cpgs(cpgs, corpus_id or src_dir.name, cpg_config=f"embedded-joern:{joern_home()}", **kw)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    m = report["metrics"]
    run = report["run"]
    t = m["totals"]
    lines: List[str] = []
    lines.append("# F2-A handler-resolution evaluation")
    lines.append("")
    lines.append(f"- corpus: `{run['corpus_id']}`")
    lines.append(f"- tool commit: `{run['tool_commit']}`")
    lines.append(f"- CPG generation: `{run['cpg_generation_config']}`")
    lines.append(f"- timestamp: {run['timestamp']}")
    lines.append("")
    lines.append("## 1. Resolution outcomes")
    lines.append("")
    lines.append(f"{t['cpgs']} CPGs, {t['actions']} action slots.")
    lines.append("")
    lines.append("| outcome | count |")
    lines.append("|---|--:|")
    for k in ("RESOLVED", "AMBIGUOUS", "UNRESOLVED"):
        lines.append(f"| {k} | {m['outcome_counts'].get(k, 0)} |")
    lines.append("")
    lines.append("## 2. Unresolved by reason and analysis-scope tier")
    lines.append("")
    lines.append("| tier | count |")
    lines.append("|---|--:|")
    for k, v in m["tier_histogram"].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("| reason | count |")
    lines.append("|---|--:|")
    for k, v in m["unresolved_reason_histogram"].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## 3. Likely backend required (with classification confidence)")
    lines.append("")
    lines.append("| backend_category | confidence | count |")
    lines.append("|---|---|--:|")
    for backend, conf_counts in m["backend_histogram"].items():
        for conf, n in conf_counts.items():
            lines.append(f"| {backend} | {conf} | {n} |")
    lines.append("")
    lines.append("## 4. Confidence / corroboration / ambiguity distributions")
    lines.append("")
    lines.append(f"- resolved confidence: {m['resolved_confidence']}")
    lines.append(f"- corroboration lift: {m['corroboration_lift']}")
    lines.append(f"- competing-candidate margin: {m['margin']}")
    lines.append(f"- within ambiguity margin: {m['within_ambiguity_margin']}")
    lines.append("")
    lines.append("## 5. Volume & performance")
    lines.append("")
    lines.append(f"- evidence volume per slot: {m['evidence_volume']}")
    lines.append(f"- candidate volume per slot: {m['candidate_volume']}")
    lines.append(f"- total runtime (s): {report['performance']['total_runtime_s']}")
    lines.append("")
    return "\n".join(lines)


def write_reports(report: Dict[str, Any], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    (out_dir / "report.md").write_text(render_markdown(report))


def deterministic_view(report: Dict[str, Any]) -> Dict[str, Any]:
    """The parts guaranteed reproducible across runs (excludes run metadata +
    wall-clock performance)."""
    return {"metrics": report["metrics"], "actions": report["actions"]}


def main() -> None:  # pragma: no cover - thin CLI wrapper
    import argparse
    from datetime import datetime, timezone

    ap = argparse.ArgumentParser(description="F2-A handler-resolution evaluation harness")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cpg-dir", type=Path, help="directory of pre-generated CPG .json files")
    g.add_argument("--source-dir", type=Path, help="directory of C/C++ sources")
    ap.add_argument("--corpus-id", type=str, default=None)
    ap.add_argument("--out", type=Path, required=True, help="output directory for report.json / report.md")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    if args.cpg_dir:
        report = evaluate_cpg_dir(args.cpg_dir, args.corpus_id, timestamp=ts)
    else:
        report = evaluate_source_dir(args.source_dir, args.corpus_id, timestamp=ts)
    write_reports(report, args.out)
    t = report["metrics"]["totals"]
    print(
        f"[f2a-eval] {t['cpgs']} CPGs, {t['actions']} actions -> "
        f"{t['resolved']} resolved / {t['ambiguous']} ambiguous / {t['unresolved']} unresolved"
    )
    print(f"[f2a-eval] reports written to {args.out}")


if __name__ == "__main__":  # pragma: no cover
    main()
