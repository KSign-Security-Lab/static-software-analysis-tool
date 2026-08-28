#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze graph JSON at scale:
- Reads JSON arrays or JSONL (optionally .gz) of graphs with {nodes:[...], edges:[...]}.
- Normalizes into two tables: nodes, edges.
- Writes sharded Parquet for scale; also writes CSV summaries.
- Computes distributions: node types, sink flags, degree stats, call names, edge flows.
- Optional charts (PNG) for quick visual checks.

Requirements:
  pip install polars pyarrow tqdm matplotlib

Usage:
  python analyze_graph_json.py \
    --input "data/**/*.jsonl.gz" \
    --outdir out \
    --format jsonl \
    --batch-size 200000 \
    --charts
"""

import argparse
import glob
import gzip
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Tuple

# Charts (optional)
import matplotlib.pyplot as plt

# Data/compute
import polars as pl
from tqdm import tqdm


def open_text(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def iter_graphs_from_file(path: str, file_format: str) -> Iterable[Dict[str, Any]]:
    """
    Yields one graph object at a time.
    file_format: 'jsonl' (one graph per line) or 'json' (array of graphs)
    """
    with open_text(path) as f:
        if file_format == "jsonl":
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
        elif file_format == "json":
            data = json.load(f)
            if isinstance(data, list):
                for g in data:
                    yield g
            else:
                # supports top-level object with list inside (rare)
                for g in data.get("graphs", []):
                    yield g
        else:
            raise ValueError("file_format must be 'json' or 'jsonl'")


def extract_rows(graph: Dict[str, Any], graph_id: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    node_rows, edge_rows = [], []
    for n in graph.get("nodes", []):
        f = n.get("features", {}) or {}
        d = n.get("debug", {}) or {}
        node_rows.append(
            {
                "graph_id": graph_id,
                "node_id": n.get("id"),
                "nodeType": f.get("nodeType"),
                "inDegreeDFG": f.get("inDegreeDFG"),
                "outDegreeDFG": f.get("outDegreeDFG"),
                "defCount": f.get("defCount"),
                "useCount": f.get("useCount"),
                "isBufferAccess": f.get("isBufferAccess"),
                "isSinkAssignment": f.get("isSinkAssignment"),
                "isSinkCallUnbounded": f.get("isSinkCallUnbounded"),
                "isSinkCallBounded": f.get("isSinkCallBounded"),
                "callName": d.get("callName"),
                "label": d.get("label"),
                "argCount": d.get("argCount"),
                "reason": d.get("reason"),
                # Keep file/type if present for per-file rollups later
                "file": d.get("file"),
                "type_dbg": d.get("type"),
            }
        )
    for e in graph.get("edges", []):
        ef = e.get("features", {}) or {}
        edge_rows.append(
            {
                "graph_id": graph_id,
                "source": e.get("source"),
                "destination": e.get("destination"),
                "flow": ef.get("flow"),
                "guard": ef.get("guard"),
            }
        )
    return node_rows, edge_rows


def write_parquet_shard(df: pl.DataFrame, outdir: str, base: str, shard_idx: int) -> str:
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{base}-{shard_idx:05d}.parquet")
    df.write_parquet(path, compression="zstd", use_pyarrow=True)
    return path


def build_summaries(nodes_glob: str, edges_glob: str, outdir: str, charts: bool):
    os.makedirs(outdir, exist_ok=True)

    nodes = pl.scan_parquet(nodes_glob)
    edges = pl.scan_parquet(edges_glob)

    # 1) Node Types — Counts
    node_type_counts = nodes.group_by("nodeType").agg(pl.len().alias("count")).sort("count", descending=True).collect()
    node_type_counts.write_csv(os.path.join(outdir, "node_types_counts.csv"))

    # 2) Sink Flags — Counts
    sink_cols = [
        "isBufferAccess",
        "isSinkAssignment",
        "isSinkCallBounded",
        "isSinkCallUnbounded",
    ]
    sink_exprs = [pl.sum(pl.col(c).cast(pl.Int64)).alias(c) for c in sink_cols]
    sink_counts = nodes.select(sink_exprs).collect()
    sink_counts.write_csv(os.path.join(outdir, "sink_flags_counts.csv"))

    # 3) Degree Stats by nodeType
    deg_stats = (
        nodes.group_by("nodeType")
        .agg(
            [
                pl.len().alias("count"),
                pl.mean("inDegreeDFG").alias("inDegreeDFG_mean"),
                pl.max("inDegreeDFG").alias("inDegreeDFG_max"),
                pl.min("inDegreeDFG").alias("inDegreeDFG_min"),
                pl.mean("outDegreeDFG").alias("outDegreeDFG_mean"),
                pl.max("outDegreeDFG").alias("outDegreeDFG_max"),
                pl.min("outDegreeDFG").alias("outDegreeDFG_min"),
                pl.mean("defCount").alias("defCount_mean"),
                pl.max("defCount").alias("defCount_max"),
                pl.min("defCount").alias("defCount_min"),
                pl.mean("useCount").alias("useCount_mean"),
                pl.max("useCount").alias("useCount_max"),
                pl.min("useCount").alias("useCount_min"),
            ]
        )
        .sort("count", descending=True)
        .collect()
    )
    deg_stats.write_csv(os.path.join(outdir, "degree_stats_by_nodeType.csv"))

    # 4) Call Names — Counts
    call_counts = nodes.group_by("callName").agg(pl.len().alias("count")).sort("count", descending=True).collect()
    call_counts.write_csv(os.path.join(outdir, "call_names_counts.csv"))

    # 5) Edge flow distribution
    edge_flows = edges.group_by("flow").agg(pl.len().alias("count")).sort("count", descending=True).collect()
    edge_flows.write_csv(os.path.join(outdir, "edge_flow_counts.csv"))

    # Optional charts
    if charts:
        # inDegreeDFG histogram
        nd = nodes.select(pl.col("inDegreeDFG")).collect()
        vals = nd["inDegreeDFG"].drop_nulls().to_list()
        if vals:
            plt.figure()
            plt.hist(vals, bins=max(10, min(50, len(set(vals)))))
            plt.title("inDegreeDFG Distribution")
            plt.xlabel("inDegreeDFG")
            plt.ylabel("Frequency")
            plt.tight_layout()
            plt.savefig(os.path.join(outdir, "hist_inDegreeDFG.png"), dpi=160)
            plt.close()

        # outDegreeDFG histogram
        nd2 = nodes.select(pl.col("outDegreeDFG")).collect()
        vals2 = nd2["outDegreeDFG"].drop_nulls().to_list()
        if vals2:
            plt.figure()
            plt.hist(vals2, bins=max(10, min(50, len(set(vals2)))))
            plt.title("outDegreeDFG Distribution")
            plt.xlabel("outDegreeDFG")
            plt.ylabel("Frequency")
            plt.tight_layout()
            plt.savefig(os.path.join(outdir, "hist_outDegreeDFG.png"), dpi=160)
            plt.close()


def main():
    ap = argparse.ArgumentParser(description="Analyze graph JSON at scale.")
    ap.add_argument("--input", required=True, help="Glob for input files, e.g. 'data/**/*.jsonl.gz'")
    ap.add_argument(
        "--format",
        choices=["jsonl", "json"],
        default="json",
        help="File format: 'jsonl' (one graph per line) or 'json' (array).",
    )
    ap.add_argument("--outdir", default="out", help="Output directory for shards and summaries.")
    ap.add_argument(
        "--batch-size",
        type=int,
        default=200_000,
        help="Rows per shard (nodes/edges separately). Tune for memory.",
    )
    ap.add_argument("--charts", action="store_true", help="Emit basic PNG charts.")
    args = ap.parse_args()

    paths = sorted(glob.glob(args.input, recursive=True))
    if not paths:
        print("No files matched --input pattern.", file=sys.stderr)
        sys.exit(2)

    os.makedirs(args.outdir, exist_ok=True)
    nodes_batch: List[Dict[str, Any]] = []
    edges_batch: List[Dict[str, Any]] = []
    node_shard_idx = 0
    edge_shard_idx = 0
    total_graphs = 0

    for path in paths:
        for graph in tqdm(
            iter_graphs_from_file(path, args.format),
            desc=f"Reading {os.path.basename(path)}",
        ):
            nrows, erows = extract_rows(graph, graph_id=total_graphs)
            total_graphs += 1
            if nrows:
                nodes_batch.extend(nrows)
            if erows:
                edges_batch.extend(erows)

            if len(nodes_batch) >= args.batch_size:
                df = pl.DataFrame(nodes_batch)
                write_parquet_shard(df, args.outdir, "nodes", node_shard_idx)
                node_shard_idx += 1
                nodes_batch.clear()

            if len(edges_batch) >= args.batch_size:
                df = pl.DataFrame(edges_batch)
                write_parquet_shard(df, args.outdir, "edges", edge_shard_idx)
                edge_shard_idx += 1
                edges_batch.clear()

    # flush remaining
    if nodes_batch:
        df = pl.DataFrame(nodes_batch)
        write_parquet_shard(df, args.outdir, "nodes", node_shard_idx)
        node_shard_idx += 1
        nodes_batch.clear()

    if edges_batch:
        df = pl.DataFrame(edges_batch)
        write_parquet_shard(df, args.outdir, "edges", edge_shard_idx)
        edge_shard_idx += 1
        edges_batch.clear()

    if node_shard_idx == 0:
        print("No nodes were parsed; nothing to summarize.", file=sys.stderr)
        sys.exit(0)
    if edge_shard_idx == 0:
        print(
            "No edges were parsed; proceeding with node-only summaries.",
            file=sys.stderr,
        )

    nodes_glob = os.path.join(args.outdir, "nodes-*.parquet")
    edges_glob = os.path.join(args.outdir, "edges-*.parquet")
    build_summaries(nodes_glob, edges_glob, args.outdir, charts=args.charts)

    print(f"Done. Graphs processed: {total_graphs}")
    print(f"Parquet shards in: {args.outdir}")
    print("Summary CSVs:")
    print("  - node_types_counts.csv")
    print("  - sink_flags_counts.csv")
    print("  - degree_stats_by_nodeType.csv")
    print("  - call_names_counts.csv")
    print("  - edge_flow_counts.csv")
    if args.charts:
        print("Charts:")
        print("  - hist_inDegreeDFG.png")
        print("  - hist_outDegreeDFG.png")


if __name__ == "__main__":
    main()
