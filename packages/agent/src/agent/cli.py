"""``agent`` -- inspect a tree from the terminal.

The same library the web API drives, without the browser. Both are thin front
ends over the same package: ``api`` imports ``agent``, never the reverse, and
the CLI does not go through HTTP -- needing a web server running before a local
directory can be analysed would be backwards.

::

    agent                        interactive: pick an endpoint, model and target
    agent index   path/to/src    index only; deterministic, no model calls
    agent inspect path/to/src    index and inspect
    agent runs                   previous runs

Run bare it prompts, which is the difference between "works" and "usable":
``AGENT_MODEL`` has to match the id the server reports, and asking the server
removes the chance of guessing wrong.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

from .config import ENV_BASE_URL, ENV_MODEL, AgentConfig
from .endpoint import Endpoint, discover
from .graph.build import run_inspection
from .index import build_index
from .runs import STATUS_DONE, STATUS_FAILED, STATUS_INSPECTING, RunPaths, list_runs, new_run
from .schema import Finding
from .tracing import status as tracing_status

SEVERITY_MARK = {"critical": "!!", "high": " !", "medium": " ~", "low": " -", "info": " ."}

#: Offered as the default target when prompting: a small labelled tree shipped
#: with the package, so a first run has something to find without the user
#: having to supply source. Absent from an installed wheel, hence the fallback.
SAMPLE_TREE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sample"

#: Enough chunks that the run is worth thinking about before starting it.
LARGE_RUN_CHUNKS = 40


def _err(message: str) -> None:
    print(f"\033[31merror:\033[0m {message}", file=sys.stderr)


def _info(message: str) -> None:
    print(f"\033[36m{message}\033[0m")


def _copy_tree(source: Path, destination: Path) -> None:
    """Copy the tree into the run workspace.

    A local path is copied rather than analysed in place so a CLI run has the
    same shape as an upload: one directory holding source, index and report,
    removable as a unit and never writing to the user's checkout.
    """
    shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=False, ignore_dangling_symlinks=True)


def _print_finding(finding: Finding) -> None:
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


# ----------------------------------------------------------------- prompting


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def _choose(prompt: str, options: list[str]) -> int:
    """Index of the chosen option. Single-option lists do not ask."""
    if len(options) == 1:
        return 0
    for number, option in enumerate(options, start=1):
        print(f"  {number}) {option}")
    while True:
        raw = _ask(prompt, "1")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        _err(f"not a choice: {raw}")


def _pick_endpoint() -> Endpoint | None:
    """Find a running server, asking if there is more than one."""
    endpoints = discover()
    if not endpoints:
        return None
    labels = [f"{e.base_url}  ({', '.join(e.models[:3])})" for e in endpoints]
    print()
    _info("Endpoints")
    return endpoints[_choose("Endpoint", labels)]


def _interactive(config: AgentConfig) -> int:
    """Prompt for everything, then run."""
    _info("SSAT agent")

    endpoint = _pick_endpoint()
    if endpoint is None:
        _err("no vLLM server is answering on port 8001 or 8000.")
        print("Start one with:  docker compose --profile vllm up -d --wait vllm", file=sys.stderr)
        return 2

    print()
    _info(f"Models served by {endpoint.base_url}")
    model = endpoint.models[_choose("Model", list(endpoint.models))]

    print()
    target = Path(_ask("Path to inspect", str(SAMPLE_TREE) if SAMPLE_TREE.is_dir() else "."))
    if not target.is_dir():
        _err(f"not a directory: {target}")
        return 2

    config.base_url = endpoint.base_url
    config.model = model
    # Exported so a nested process, or the user's next command, agrees.
    os.environ[ENV_BASE_URL] = endpoint.base_url
    os.environ[ENV_MODEL] = model

    print()
    _info("Indexing (deterministic, no model calls)")
    paths = new_run(config)
    _copy_tree(target.resolve(), paths.source)
    store = paths.store()
    try:
        index_result = build_index(paths.source, store)
    finally:
        store.close()

    print(f"  {json.dumps(index_result.as_dict())}")
    print()
    _info("Ready")
    print(f"  endpoint  {config.base_url}")
    print(f"  model     {config.model}")
    print(f"  target    {target}")
    print(f"  chunks    {index_result.chunks}  (one model call each, plus one per candidate finding)")
    trace = tracing_status()
    print(f"  tracing   {'on -> ' + trace['project'] if trace['enabled'] else 'off'}")
    if trace["detail"] and trace["enabled"]:
        print(f"            {trace['detail']}")
    print()

    choice = _choose("Choice", ["inspect now", "stop here, print the equivalent command"])
    if choice == 1:
        print()
        print(f"export {ENV_BASE_URL}={config.base_url}")
        print(f"export {ENV_MODEL}={config.model}")
        print(f"agent inspect -v {target}")
        return 0

    if index_result.chunks > LARGE_RUN_CHUNKS:
        print(f"\033[33mwarning:\033[0m {index_result.chunks} chunks is a long run")
    print()
    _info("Inspecting -- minutes, not seconds. Ctrl-C is safe: progress is kept.")
    print()
    return _inspect_run(paths, config, index_result.as_dict())


# ------------------------------------------------------------------ commands


def _inspect_run(paths: RunPaths, config: AgentConfig, index_stats: dict[str, int]) -> int:
    """Drive an already-indexed run to completion and print the report."""

    def emit(event: str, payload: object) -> None:
        if event == "chunk_finished" and isinstance(payload, dict):
            stats = payload.get("stats", {})
            done = stats.get("chunks_inspected", 0)
            total = stats.get("chunks_total", 0)
            found = len(payload.get("findings", []))
            suffix = f"  +{found}" if found else ""
            print(f"\r  [{done}/{total}] {str(payload.get('symbol', ''))[:40]}{suffix}", end="", flush=True)

    store = paths.store()
    try:
        paths.set_status(STATUS_INSPECTING)
        report = run_inspection(
            run_id=paths.run_id,
            root=paths.source,
            store=store,
            config=config,
            emit=emit,
            index_stats=index_stats,
        )
    except Exception as err:  # noqa: BLE001 - the CLI reports rather than traces
        paths.set_status(STATUS_FAILED, error=str(err))
        _err(f"inspection failed: {err}")
        return 1
    finally:
        store.close()

    paths.save_report(report)
    paths.set_status(STATUS_DONE)

    print("\n")
    for finding in report.sorted_findings():
        _print_finding(finding)

    stats = report.stats
    print(
        f"{len(report.findings)} finding(s) from {stats.chunks_inspected} chunk(s). "
        f"{stats.candidates} candidate(s), {stats.refuted} refuted, "
        f"{stats.dropped_unlocatable} dropped as unlocatable."
    )
    print(f"report: {paths.report_path}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    source = Path(args.path).resolve()
    if not source.is_dir():
        _err(f"not a directory: {source}")
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
        _err(f"not a directory: {source}")
        return 2

    config = AgentConfig()
    try:
        config.require_model()
    except RuntimeError as err:
        _err(str(err))
        print("Or run `agent` with no arguments to pick one interactively.", file=sys.stderr)
        return 2

    paths = new_run(config)
    _copy_tree(source, paths.source)
    store = paths.store()
    try:
        index_result = build_index(paths.source, store)
    finally:
        store.close()
    print(f"run {paths.run_id}: indexed {index_result.files_indexed} files, {index_result.chunks} chunks")

    return _inspect_run(paths, config, index_result.as_dict())


def cmd_runs(args: argparse.Namespace) -> int:
    runs = list_runs()
    if not runs:
        print("no runs")
        return 0
    for run in runs:
        index = run.get("index", {})
        print(f"{run.get('run_id', '?')}  {run.get('status', '?'):<12} {index.get('chunks', '?')} chunks")
    return 0


def cmd_endpoints(args: argparse.Namespace) -> int:
    """What is reachable, and what it serves. Answers 'why does nothing work'.

    Tracing status is printed either way. It is a separate question from whether
    a model server is up, and the whole point of this command is to answer "what
    is my environment actually doing" in one place.
    """
    endpoints = discover()
    for endpoint in endpoints:
        print(endpoint.base_url)
        for model in endpoint.models:
            print(f"  {model}")
    if not endpoints:
        print("no vLLM server answering on port 8001 or 8000")
        print("start one with: docker compose --profile vllm up -d --wait vllm")

    trace = tracing_status()
    print()
    print(f"langsmith: {'on -> ' + trace['project'] if trace['enabled'] else 'off'}")
    if trace["detail"]:
        print(f"  {trace['detail']}")
    # Non-zero only for the thing that blocks a run; tracing being off does not.
    return 0 if endpoints else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="LLM-based static analysis, one chunk at a time. Run with no arguments to be prompted.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log model calls and dropped anchors")
    subparsers = parser.add_subparsers(dest="command")

    index_parser = subparsers.add_parser("index", help="Index a tree without calling a model")
    index_parser.add_argument("path", help="Directory to index")
    index_parser.set_defaults(func=cmd_index)

    inspect_parser = subparsers.add_parser("inspect", help="Index and inspect a tree")
    inspect_parser.add_argument("path", help="Directory to inspect")
    inspect_parser.set_defaults(func=cmd_inspect)

    subparsers.add_parser("runs", help="List previous runs").set_defaults(func=cmd_runs)
    subparsers.add_parser("endpoints", help="Show reachable servers and their models").set_defaults(func=cmd_endpoints)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command is None:
        if not sys.stdin.isatty():
            build_parser().print_help()
            return 1
        return _interactive(AgentConfig())

    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
