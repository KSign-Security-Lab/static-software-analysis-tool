"""``agent`` -- inspect a tree from the terminal.

The same loop the web page drives, without the browser. It exists because
iterating on prompts and context packs through a UI is slow, and because a
report is useful in CI.

::

    agent inspect path/to/src
    agent index   path/to/src          # index only, no model calls
    agent runs                         # what has been inspected
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import AgentConfig
from .graph.build import run_inspection
from .index import build_index
from .runs import STATUS_DONE, STATUS_FAILED, STATUS_INSPECTING, list_runs, new_run
from .schema import Finding

SEVERITY_MARK = {"critical": "!!", "high": " !", "medium": " ~", "low": " -", "info": " ."}


def _copy_tree(source: Path, destination: Path) -> None:
    """Copy the tree into the run workspace.

    A local path is copied rather than inspected in place so a CLI run has the
    same shape as an upload: one directory holding source, index and report,
    removable as a unit and never writing to the user's checkout.
    """
    import shutil

    shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=False, ignore_dangling_symlinks=True)


def _print_finding(finding: Finding, root: Path) -> None:
    mark = SEVERITY_MARK.get(finding.severity, "  ")
    location = f"{finding.primary.file}:{finding.primary.start_line}:{finding.primary.start_column}"
    cwe = f" [{finding.cwe}]" if finding.cwe else ""
    unverified = "" if finding.verified else "  (unverified)"
    print(f"{mark} {location}: {finding.severity}{cwe} {finding.title}{unverified}")
    print(f"     {finding.primary.excerpt.strip()[:100]}")
    print(f"     {finding.explanation.strip()[:300]}")
    for item in finding.evidence:
        print(f"       - [{item.role}] {item.span.file}:{item.span.start_line} {item.note[:120]}")
    print(f"     fix: {finding.remediation.summary}")
    print()


def cmd_index(args: argparse.Namespace) -> int:
    source = Path(args.path).resolve()
    if not source.is_dir():
        print(f"not a directory: {source}", file=sys.stderr)
        return 2

    paths = new_run()
    _copy_tree(source, paths.source)
    store = paths.store()
    try:
        result = build_index(paths.source, store)
        order = store.order()
    finally:
        store.close()

    print(f"run {paths.run_id}: {json.dumps(result.as_dict())}")
    print(f"inspection order: {len(order)} chunks (callees before callers)")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    source = Path(args.path).resolve()
    if not source.is_dir():
        print(f"not a directory: {source}", file=sys.stderr)
        return 2

    config = AgentConfig()
    try:
        config.require_model()
    except RuntimeError as err:
        print(str(err), file=sys.stderr)
        return 2

    paths = new_run()
    _copy_tree(source, paths.source)
    store = paths.store()

    def emit(event: str, payload: object) -> None:
        if event == "chunk_finished" and isinstance(payload, dict):
            stats = payload.get("stats", {})
            done = stats.get("chunks_inspected", 0)
            total = stats.get("chunks_total", 0)
            found = len(payload.get("findings", []))
            suffix = f"  +{found}" if found else ""
            print(f"\r  [{done}/{total}] {payload.get('symbol', '')[:40]}{suffix}", end="", flush=True)

    try:
        index_result = build_index(paths.source, store)
        print(f"run {paths.run_id}: indexed {index_result.files_indexed} files, {index_result.chunks} chunks")
        paths.set_status(STATUS_INSPECTING)

        report = run_inspection(
            run_id=paths.run_id,
            root=paths.source,
            store=store,
            config=config,
            emit=emit,
            index_stats=index_result.as_dict(),
        )
    except Exception as err:  # noqa: BLE001 - the CLI reports rather than traces
        paths.set_status(STATUS_FAILED, error=str(err))
        print(f"\ninspection failed: {err}", file=sys.stderr)
        return 1
    finally:
        store.close()

    paths.save_report(report)
    paths.set_status(STATUS_DONE)

    print("\n")
    for finding in report.sorted_findings():
        _print_finding(finding, paths.source)

    stats = report.stats
    print(
        f"{len(report.findings)} finding(s) from {stats.chunks_inspected} chunk(s). "
        f"{stats.candidates} candidate(s), {stats.refuted} refuted, "
        f"{stats.dropped_unlocatable} dropped as unlocatable."
    )
    print(f"report: {paths.report_path}")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    runs = list_runs()
    if not runs:
        print("no runs")
        return 0
    for run in runs:
        index = run.get("index", {})
        print(f"{run.get('run_id', '?')}  {run.get('status', '?'):<12} {index.get('chunks', '?')} chunks")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="LLM-based static analysis, one chunk at a time",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log model and tool activity")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Index a tree without calling a model")
    index_parser.add_argument("path", help="Directory to index")
    index_parser.set_defaults(func=cmd_index)

    inspect_parser = subparsers.add_parser("inspect", help="Index and inspect a tree")
    inspect_parser.add_argument("path", help="Directory to inspect")
    inspect_parser.set_defaults(func=cmd_inspect)

    runs_parser = subparsers.add_parser("runs", help="List previous runs")
    runs_parser.set_defaults(func=cmd_runs)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
