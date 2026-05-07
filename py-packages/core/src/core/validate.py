import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class Limits:
    graph_details: int = 10
    node_sample: int = 100
    edge_sample: int = 100
    feature_sample: int = 50
    message_sample: int = 50


def find_pairs(dfg_py_root: Path, dfg_root: Path) -> List[Tuple[Path, Path]]:
    pairs: List[Tuple[Path, Path]] = []
    for path in dfg_py_root.rglob("*_template_dfg.json"):
        rel = path.relative_to(dfg_py_root)
        counterpart_rel = Path(str(rel).replace("_template_dfg.json", "_dfg.json"))
        counterpart = dfg_root / counterpart_rel
        if counterpart.exists():
            pairs.append((path, counterpart))
    return pairs


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_graph_list(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        return [g for g in obj if isinstance(g, dict)]
    if isinstance(obj, dict):
        return [obj]
    return []


def _normalize_py_node(node: Dict[str, Any], fallback_idx: int) -> Dict[str, Any]:
    sid = node.get("sid")
    if not isinstance(sid, int):
        sid = fallback_idx
    feat = node.get("feat") or {}
    features = {
        "nodeType": feat.get("node_type_id", "Unknown"),
        "inDegreeDFG": int(feat.get("in_degree_dfg", 0) or 0),
        "outDegreeDFG": int(feat.get("out_degree_dfg", 0) or 0),
        "defCount": int(feat.get("def_count", 0) or 0),
        "useCount": int(feat.get("use_count", 0) or 0),
        "isBufferAccess": bool(feat.get("is_buffer_access", False)),
        "isSinkAssignment": bool(feat.get("is_sink_assign", False)),
        "isSinkCallUnbounded": bool(feat.get("is_sink_call_unbounded", False)),
        "isSinkCallBounded": bool(feat.get("is_sink_call_bounded", False)),
        "callDestinationIndexed": bool(feat.get("call_dst_indexed", False)),
        "callLengthLinkedToDestination": bool(feat.get("call_len_linked_to_dst", False)),
        "callSizeNonConstant": bool(feat.get("call_size_nonconst", False)),
        "callDangerUnbounded": bool(feat.get("call_danger_unbounded", False)),
    }
    node_id = node.get("id")
    if not isinstance(node_id, int):
        node_id = sid
    return {
        "sid": sid,
        "id": node_id,
        "features": features,
        "debug": node.get("debug"),
    }


def _normalize_py_edges(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges_src = graph.get("edges") or graph.get("edge_list") or graph.get("dfg_edges") or []
    edges: List[Dict[str, Any]] = []
    if isinstance(edges_src, list):
        for entry in edges_src:
            if not isinstance(entry, dict):
                continue
            s = entry.get("source") or entry.get("src") or entry.get("from")
            t = entry.get("destination") or entry.get("dst") or entry.get("to")
            if isinstance(s, int) and isinstance(t, int):
                feat = entry.get("feat") or entry.get("features") or {}
                edges.append(
                    {
                        "source": s,
                        "destination": t,
                        "features": {
                            "flow": feat.get("flow", "BASE"),
                            "guard": feat.get("guard", "NONE"),
                            "hasLowerGuard": bool(
                                feat.get("has_lower_guard", feat.get("hasLowerGuard", False))
                            ),
                            "hasUpperGuard": bool(
                                feat.get("has_upper_guard", feat.get("hasUpperGuard", False))
                            ),
                            "upperGuardNormalization": int(
                                feat.get(
                                    "upper_guard_normalization",
                                    feat.get("upperGuardNormalization", 0),
                                )
                                or 0
                            ),
                        },
                        "debug": entry.get("debug"),
                    }
                )
    return edges


def normalize_py_graphs(graphs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, graph in enumerate(graphs):
        if not isinstance(graph, dict):
            continue
        if isinstance(graph.get("nodes"), list) and graph["nodes"]:
            first = graph["nodes"][0]
            if isinstance(first, dict) and "features" in first:
                normalized.append({"nodes": graph.get("nodes", []), "edges": graph.get("edges", [])})
                continue
        nodes_src = graph.get("nodes", [])
        nodes = [
            _normalize_py_node(node, fallback_idx=i)
            for i, node in enumerate(nodes_src)
            if isinstance(node, dict)
        ]
        edges = _normalize_py_edges(graph)
        normalized.append({"nodes": nodes, "edges": edges})
    return normalized


def _graph_nodes(graph: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not graph or not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [n for n in nodes if isinstance(n, dict)]


def _graph_edges(graph: Optional[Dict[str, Any]]) -> List[Any]:
    if not graph or not isinstance(graph, dict):
        return []
    edges = graph.get("edges")
    if not isinstance(edges, list):
        edges = graph.get("dfg_edges") or graph.get("edges_dfg") or graph.get("edge_list")
    return edges if isinstance(edges, list) else []


def _collect_node_ids(nodes: Iterable[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    for node in nodes:
        node_id = node.get("id")
        if isinstance(node_id, int):
            ids.append(node_id)
    return ids


def _edge_key(edge: Any) -> Optional[Tuple[int, int]]:
    if isinstance(edge, dict):
        s = edge.get("source") or edge.get("src") or edge.get("from")
        t = edge.get("destination") or edge.get("dst") or edge.get("to")
        if isinstance(s, int) and isinstance(t, int):
            return (s, t)
    elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
        s, t = edge[0], edge[1]
        if isinstance(s, int) and isinstance(t, int):
            return (s, t)
    return None


def _collect_edge_keys(edges: Iterable[Any]) -> List[Tuple[int, int]]:
    result: List[Tuple[int, int]] = []
    for entry in edges:
        key = _edge_key(entry)
        if key is not None:
            result.append(key)
    return result


def _feature_diff_info(
    py_nodes: Sequence[Dict[str, Any]],
    dfg_nodes: Sequence[Dict[str, Any]],
    sample_limit: int,
) -> Dict[str, Any]:
    sample: List[Dict[str, Any]] = []
    total = 0
    counts_by_key: Dict[str, int] = {}
    dfg_map = {
        node.get("id"): node
        for node in dfg_nodes
        if isinstance(node.get("id"), int)
    }
    for py_node in py_nodes:
        node_id = py_node.get("id")
        if not isinstance(node_id, int):
            continue
        dfg_node = dfg_map.get(node_id)
        if not dfg_node:
            continue
        py_feat = py_node.get("features") or {}
        dfg_feat = dfg_node.get("features") or {}
        keys = sorted(set(py_feat.keys()) | set(dfg_feat.keys()))
        changes: List[Dict[str, Any]] = []
        for key in keys:
            if py_feat.get(key) != dfg_feat.get(key):
                changes.append({"key": key, "python": py_feat.get(key), "typescript": dfg_feat.get(key)})
                counts_by_key[key] = counts_by_key.get(key, 0) + 1
        if changes:
            total += 1
            if len(sample) < sample_limit:
                sample.append({"nodeId": node_id, "changes": changes})
    return {"count": total, "sample": sample, "countsByKey": counts_by_key}


def _graph_status(has_diff: bool, py_graph: Optional[Dict[str, Any]], dfg_graph: Optional[Dict[str, Any]]) -> str:
    if py_graph is None or dfg_graph is None:
        return "missing"
    return "diff" if has_diff else "ok"


def build_graph_diff(
    index: int,
    py_graph: Optional[Dict[str, Any]],
    dfg_graph: Optional[Dict[str, Any]],
    limits: Limits,
    include_payload: bool,
) -> Dict[str, Any]:
    py_nodes = _graph_nodes(py_graph)
    dfg_nodes = _graph_nodes(dfg_graph)
    py_edges_raw = _graph_edges(py_graph)
    dfg_edges_raw = _graph_edges(dfg_graph)
    py_edges = _collect_edge_keys(py_edges_raw)
    dfg_edges = _collect_edge_keys(dfg_edges_raw)

    py_node_ids = set(_collect_node_ids(py_nodes))
    dfg_node_ids = set(_collect_node_ids(dfg_nodes))
    only_py_nodes = sorted(py_node_ids - dfg_node_ids)
    only_dfg_nodes = sorted(dfg_node_ids - py_node_ids)
    only_py_edges = sorted(set(py_edges) - set(dfg_edges))
    only_dfg_edges = sorted(set(dfg_edges) - set(py_edges))
    feature_info = _feature_diff_info(py_nodes, dfg_nodes, limits.feature_sample)

    node_count_mismatch = len(py_nodes) != len(dfg_nodes)
    edge_count_mismatch = len(py_edges) != len(dfg_edges)
    has_missing_graph = py_graph is None or dfg_graph is None
    has_diff = bool(
        has_missing_graph
        or node_count_mismatch
        or edge_count_mismatch
        or only_py_nodes
        or only_dfg_nodes
        or only_py_edges
        or only_dfg_edges
        or feature_info["count"]
    )

    diff_payload = {
        "hasDiff": has_diff,
        "nodeCountMismatch": node_count_mismatch,
        "edgeCountMismatch": edge_count_mismatch,
        "missing": {
            "pythonGraph": py_graph is None,
            "typescriptGraph": dfg_graph is None,
        },
        "nodes": {
            "onlyPython": {
                "count": len(only_py_nodes),
                "sample": only_py_nodes[: limits.node_sample],
            },
            "onlyTypescript": {
                "count": len(only_dfg_nodes),
                "sample": only_dfg_nodes[: limits.node_sample],
            },
            "intersection": len(py_node_ids & dfg_node_ids),
        },
        "edges": {
            "onlyPython": {
                "count": len(only_py_edges),
                "sample": [f"{src}->{dst}" for src, dst in only_py_edges[: limits.edge_sample]],
            },
            "onlyTypescript": {
                "count": len(only_dfg_edges),
                "sample": [
                    f"{src}->{dst}" for src, dst in only_dfg_edges[: limits.edge_sample]
                ],
            },
            "intersection": len(set(py_edges) & set(dfg_edges)),
        },
        "features": feature_info,
    }

    if "countsByKey" in feature_info:
        diff_payload["features"]["countsByKey"] = feature_info["countsByKey"]

    payload: Dict[str, Any] = {
        "index": index,
        "status": _graph_status(has_diff, py_graph, dfg_graph),
        "python": {
            "nodeCount": len(py_nodes),
            "edgeCount": len(py_edges),
        },
        "typescript": {
            "nodeCount": len(dfg_nodes),
            "edgeCount": len(dfg_edges),
        },
        "diff": diff_payload,
    }

    if include_payload:
        payload["pythonGraph"] = py_graph
        payload["typescriptGraph"] = dfg_graph

    return payload


def _graph_messages(graph: Dict[str, Any]) -> List[str]:
    idx = graph["index"]
    diff = graph["diff"]
    messages: List[str] = []
    if diff["missing"]["pythonGraph"] and not diff["missing"]["typescriptGraph"]:
        messages.append(f"graph[{idx}] missing python graph")
    if diff["missing"]["typescriptGraph"] and not diff["missing"]["pythonGraph"]:
        messages.append(f"graph[{idx}] missing typescript graph")
    if diff["nodeCountMismatch"]:
        messages.append(
            f"graph[{idx}] node count mismatch: python={graph['python']['nodeCount']} vs typescript={graph['typescript']['nodeCount']}"
        )
    if diff["edgeCountMismatch"]:
        messages.append(
            f"graph[{idx}] edge count mismatch: python={graph['python']['edgeCount']} vs typescript={graph['typescript']['edgeCount']}"
        )
    if diff["nodes"]["onlyPython"]["count"]:
        messages.append(
            f"graph[{idx}] node ids only in python (sample={diff['nodes']['onlyPython']['sample'][:5]})"
        )
    if diff["nodes"]["onlyTypescript"]["count"]:
        messages.append(
            f"graph[{idx}] node ids only in typescript (sample={diff['nodes']['onlyTypescript']['sample'][:5]})"
        )
    if diff["edges"]["onlyPython"]["count"]:
        messages.append(
            f"graph[{idx}] edges only in python (sample={diff['edges']['onlyPython']['sample'][:5]})"
        )
    if diff["edges"]["onlyTypescript"]["count"]:
        messages.append(
            f"graph[{idx}] edges only in typescript (sample={diff['edges']['onlyTypescript']['sample'][:5]})"
        )
    if diff["features"]["count"]:
        messages.append(
            f"graph[{idx}] {diff['features']['count']} node(s) with differing features"
        )
    return messages


def _total_counts(graphs: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    nodes = 0
    edges = 0
    for graph in graphs:
        nodes += len(_graph_nodes(graph))
        edges += len(_collect_edge_keys(_graph_edges(graph)))
    return {
        "graphs": len(graphs),
        "nodes": nodes,
        "edges": edges,
    }

DEFAULT_LIMITS = Limits()


def _cleanup_legacy(pair_dir: Path) -> None:
    for name in ("py_normalized.json", "dfg.json", "diffs.txt", "report.html"):
        try:
            (pair_dir / name).unlink()
        except FileNotFoundError:
            continue


def _read_existing_verdict(pair_dir: Path) -> Optional[Dict[str, Any]]:
    verdict_file = pair_dir / "verdict.json"
    if not verdict_file.exists():
        return None
    try:
        return json.loads(verdict_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_pair_report(
    py_graphs_raw: List[Dict[str, Any]],
    dfg_graphs_raw: List[Dict[str, Any]],
    limits: Limits,
    include_graph_payload: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    graphs: List[Dict[str, Any]] = []
    messages: List[str] = []
    summary_counts = {
        "graphsProcessed": 0,
        "graphsWithDiffs": 0,
        "nodeCountMismatches": 0,
        "edgeCountMismatches": 0,
        "pythonOnlyNodes": 0,
        "typescriptOnlyNodes": 0,
        "pythonOnlyEdges": 0,
        "typescriptOnlyEdges": 0,
        "featureDiffNodes": 0,
        "missingPythonGraphs": 0,
        "missingTypescriptGraphs": 0,
        "featureDiffByKey": {},
    }

    max_len = max(len(py_graphs_raw), len(dfg_graphs_raw))
    for idx in range(max_len):
        py_graph = py_graphs_raw[idx] if idx < len(py_graphs_raw) else None
        dfg_graph = dfg_graphs_raw[idx] if idx < len(dfg_graphs_raw) else None
        include_payload = include_graph_payload and idx < limits.graph_details
        graph = build_graph_diff(idx, py_graph, dfg_graph, limits, include_payload)
        summary_counts["graphsProcessed"] += 1
        if graph["diff"]["missing"]["pythonGraph"]:
            summary_counts["missingPythonGraphs"] += 1
        if graph["diff"]["missing"]["typescriptGraph"]:
            summary_counts["missingTypescriptGraphs"] += 1
        if graph["diff"]["nodeCountMismatch"]:
            summary_counts["nodeCountMismatches"] += 1
        if graph["diff"]["edgeCountMismatch"]:
            summary_counts["edgeCountMismatches"] += 1
        summary_counts["pythonOnlyNodes"] += graph["diff"]["nodes"]["onlyPython"]["count"]
        summary_counts["typescriptOnlyNodes"] += graph["diff"]["nodes"]["onlyTypescript"]["count"]
        summary_counts["pythonOnlyEdges"] += graph["diff"]["edges"]["onlyPython"]["count"]
        summary_counts["typescriptOnlyEdges"] += graph["diff"]["edges"]["onlyTypescript"]["count"]
        summary_counts["featureDiffNodes"] += graph["diff"]["features"]["count"]
        counts_by_key = graph["diff"]["features"].get("countsByKey", {}) or {}
        feature_summary = summary_counts["featureDiffByKey"]
        for key, value in counts_by_key.items():
            feature_summary[key] = feature_summary.get(key, 0) + int(value)
        if graph["diff"]["hasDiff"]:
            summary_counts["graphsWithDiffs"] += 1
        if idx < limits.graph_details:
            graphs.append(graph)
        if graph["diff"]["hasDiff"] and len(messages) < limits.message_sample:
            messages.extend(_graph_messages(graph))
    return graphs, summary_counts, messages


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _relative_pair_dir(report_root: Path, dfg_py_root: Path, py_path: Path) -> Path:
    rel = py_path.relative_to(dfg_py_root)
    return (report_root / rel.parent / rel.stem).resolve()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare Python and TypeScript generated DFGs")
    parser.add_argument(
        "--dfg-root",
        type=Path,
        default=Path("../../data/dfg"),
        help="Directory containing TypeScript generated DFG JSON files.",
    )
    parser.add_argument(
        "--dfg-python-root",
        type=Path,
        default=Path("../../data/dfg-python"),
        help="Directory containing Python generated DFG JSON files.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("../../data/validate_report"),
        help="Directory to write comparison reports.",
    )
    parser.add_argument(
        "--graph-limit",
        type=int,
        default=DEFAULT_LIMITS.graph_details,
        help="Number of graph details to embed per pair.",
    )
    parser.add_argument(
        "--node-sample",
        type=int,
        default=DEFAULT_LIMITS.node_sample,
        help="Sample size for node id differences.",
    )
    parser.add_argument(
        "--edge-sample",
        type=int,
        default=DEFAULT_LIMITS.edge_sample,
        help="Sample size for edge differences.",
    )
    parser.add_argument(
        "--feature-sample",
        type=int,
        default=DEFAULT_LIMITS.feature_sample,
        help="Sample size for feature difference reporting.",
    )
    parser.add_argument(
        "--message-sample",
        type=int,
        default=DEFAULT_LIMITS.message_sample,
        help="Maximum number of diff messages per pair.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    limits = Limits(
        graph_details=max(1, args.graph_limit),
        node_sample=max(1, args.node_sample),
        edge_sample=max(1, args.edge_sample),
        feature_sample=max(1, args.feature_sample),
        message_sample=max(1, args.message_sample),
    )

    dfg_root = args.dfg_root.resolve()
    dfg_py_root = args.dfg_python_root.resolve()
    report_dir = args.report_dir.resolve()

    if not dfg_root.exists() or not dfg_py_root.exists():
        logging.error("Invalid roots: dfg=%s dfg-python=%s", dfg_root, dfg_py_root)
        return 2

    report_dir.mkdir(parents=True, exist_ok=True)

    pairs = find_pairs(dfg_py_root, dfg_root)
    if not pairs:
        logging.warning("No matching *_template_dfg.json files under %s", dfg_py_root)
        return 1

    total_pairs = len(pairs)
    status_counter: Counter[str] = Counter()
    index_entries: List[Dict[str, Any]] = []
    aggregate = {
        "totalPairs": total_pairs,
        "graphsProcessed": 0,
        "graphsWithDiffs": 0,
        "pythonOnlyNodes": 0,
        "typescriptOnlyNodes": 0,
        "pythonOnlyEdges": 0,
        "typescriptOnlyEdges": 0,
        "featureDiffNodes": 0,
        "pythonTotals": {"graphs": 0, "nodes": 0, "edges": 0},
        "typescriptTotals": {"graphs": 0, "nodes": 0, "edges": 0},
        "featureDiffByKey": {},
    }

    for idx, (py_path, dfg_path) in enumerate(pairs, start=1):
        pair_dir = _relative_pair_dir(report_dir, dfg_py_root, py_path)
        slug = str(pair_dir.relative_to(report_dir)).replace("\\", "/")
        pair_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_legacy(pair_dir)

        logging.debug("[%s/%s] Comparing %s", idx, total_pairs, slug)

        try:
            py_json = load_json(py_path)
            dfg_json = load_json(dfg_path)
            py_graphs = normalize_py_graphs(_ensure_graph_list(py_json))
            dfg_graphs = _ensure_graph_list(dfg_json)
            graphs, summary_counts, messages = build_pair_report(
                py_graphs, dfg_graphs, limits, include_graph_payload=True
            )
            status = "ok" if summary_counts["graphsWithDiffs"] == 0 else "diff"
            summary_counts["pythonTotals"] = _total_counts(py_graphs)
            summary_counts["typescriptTotals"] = _total_counts(dfg_graphs)
            status_counter.update([status])
            aggregate["graphsProcessed"] += summary_counts["graphsProcessed"]
            aggregate["graphsWithDiffs"] += summary_counts["graphsWithDiffs"]
            aggregate["pythonOnlyNodes"] += summary_counts["pythonOnlyNodes"]
            aggregate["typescriptOnlyNodes"] += summary_counts["typescriptOnlyNodes"]
            aggregate["pythonOnlyEdges"] += summary_counts["pythonOnlyEdges"]
            aggregate["typescriptOnlyEdges"] += summary_counts["typescriptOnlyEdges"]
            aggregate["featureDiffNodes"] += summary_counts["featureDiffNodes"]
            for key in ("pythonTotals", "typescriptTotals"):
                agg_slot = aggregate[key]
                pair_slot = summary_counts[key]
                agg_slot["graphs"] += pair_slot.get("graphs", 0)
                agg_slot["nodes"] += pair_slot.get("nodes", 0)
                agg_slot["edges"] += pair_slot.get("edges", 0)
            for feature_key, value in summary_counts.get("featureDiffByKey", {}).items():
                feature_totals = aggregate["featureDiffByKey"]
                feature_totals[feature_key] = feature_totals.get(feature_key, 0) + int(value)
            verdict = _read_existing_verdict(pair_dir)
            report_payload = {
                "slug": slug,
                "generatedAt": None,
                "status": status,
                "limits": asdict(limits),
                "summary": summary_counts,
                "messages": messages[: limits.message_sample],
                "paths": {
                    "python": {
                        "absolute": str(py_path.resolve()),
                        "relative": str(py_path.relative_to(dfg_py_root)),
                    },
                    "typescript": {
                        "absolute": str(dfg_path.resolve()),
                        "relative": str(dfg_path.relative_to(dfg_root)),
                    },
                },
                "verdict": verdict,
                "graphs": graphs,
            }
        except Exception as exc:  # noqa: PERF203
            logging.exception("Failed to compare %s", slug)
            status = "error"
            status_counter.update([status])
            verdict = _read_existing_verdict(pair_dir)
            report_payload = {
                "slug": slug,
                "generatedAt": None,
                "status": status,
                "limits": asdict(limits),
                "summary": {},
                "messages": [f"exception: {exc}"],
                "paths": {
                    "python": {
                        "absolute": str(py_path.resolve()),
                        "relative": str(py_path.relative_to(dfg_py_root)),
                    },
                    "typescript": {
                        "absolute": str(dfg_path.resolve()),
                        "relative": str(dfg_path.relative_to(dfg_root)),
                    },
                },
                "verdict": verdict,
                "graphs": [],
            }
        generated_at = datetime.now(timezone.utc).isoformat()
        report_payload["generatedAt"] = generated_at

        _write_json(pair_dir / "report.json", report_payload)

        index_entry = {
            "slug": slug,
            "status": status,
            "pythonPath": report_payload["paths"]["python"]["relative"],
            "typescriptPath": report_payload["paths"]["typescript"]["relative"],
            "messages": report_payload["messages"][:5],
            "updatedAt": generated_at,
            "verdict": report_payload.get("verdict"),
        }
        if report_payload["summary"]:
            index_entry["summary"] = {
                "graphsProcessed": report_payload["summary"].get("graphsProcessed", 0),
                "graphsWithDiffs": report_payload["summary"].get("graphsWithDiffs", 0),
                "pythonOnlyNodes": report_payload["summary"].get("pythonOnlyNodes", 0),
                "typescriptOnlyNodes": report_payload["summary"].get("typescriptOnlyNodes", 0),
                "pythonOnlyEdges": report_payload["summary"].get("pythonOnlyEdges", 0),
                "typescriptOnlyEdges": report_payload["summary"].get("typescriptOnlyEdges", 0),
                "featureDiffNodes": report_payload["summary"].get("featureDiffNodes", 0),
            }
        index_entries.append(index_entry)

    aggregate["statusCounts"] = dict(status_counter)
    index_payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "limits": asdict(limits),
        "roots": {
            "python": str(dfg_py_root),
            "typescript": str(dfg_root),
            "report": str(report_dir),
        },
        "summary": aggregate,
        "pairs": sorted(
            index_entries,
            key=lambda item: (0 if item["status"] != "ok" else 1, item["slug"]),
        ),
    }

    _write_json(report_dir / "index.json", index_payload)

    ok = status_counter.get("ok", 0)
    diff = status_counter.get("diff", 0)
    err = status_counter.get("error", 0)
    print(
        f"Validated {total_pairs} pair(s): {ok} ok, {diff} with diffs, {err} errors. Index: {report_dir / 'index.json'}"
    )
    return 0 if diff == 0 and err == 0 else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
