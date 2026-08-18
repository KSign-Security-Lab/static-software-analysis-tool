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
import sys
from pathlib import Path

from .config import ENV_BASE_URL, ENV_MODEL, AgentConfig
from .endpoint import Endpoint, discover
from .graph.build import run_inspection
from .runs import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INSPECTING,
    Run,
    index_run,
    list_runs,
    new_run,
    write_files,
)
from .schema import Finding, Report
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


def _load_tree(source: Path, run: Run) -> int:
    """Read a local directory into the run. Returns the file count.

    Was `shutil.copytree` into the run's workspace. There is no workspace: the
    files become rows, which is the same bargain as before -- the user's
    checkout is read and never written -- reached without a second copy on disk.
    """
    files: dict[str, bytes] = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        files[path.relative_to(source).as_posix()] = path.read_bytes()
    return write_files(run, files)


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
    run = new_run(config)
    _load_tree(target.resolve(), run)
    index_result = index_run(run)

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
    return _inspect_run(run, config, index_result.as_dict())


# ------------------------------------------------------------------ commands


def _inspect_run(run: Run, config: AgentConfig, index_stats: dict[str, int]) -> int:
    """Drive an already-indexed run to completion and print the report."""

    def emit(event: str, payload: object) -> None:
        if event == "chunk_finished" and isinstance(payload, dict):
            stats = payload.get("stats", {})
            done = stats.get("chunks_inspected", 0)
            total = stats.get("chunks_total", 0)
            found = len(payload.get("findings", []))
            suffix = f"  +{found}" if found else ""
            print(f"\r  [{done}/{total}] {str(payload.get('symbol', ''))[:40]}{suffix}", end="", flush=True)

    store = run.store()
    # Recorded here too, so a run started from the terminal is inspectable in
    # the web trace view afterwards. They share a database.
    spans = run.spans()
    spans.clear()
    try:
        run.set_status(STATUS_INSPECTING)
        report = run_inspection(
            run_id=run.run_id,
            files=run.file_contents(),
            store=store,
            config=config,
            emit=emit,
            index_stats=index_stats,
            spans=spans,
        )
    except Exception as err:  # noqa: BLE001 - the CLI reports rather than traces
        run.set_status(STATUS_FAILED, error=str(err))
        _err(f"inspection failed: {err}")
        return 1
    finally:
        store.close()
        spans.close()

    run.save_report(report)
    run.set_status(STATUS_DONE)

    print("\n")
    for finding in report.sorted_findings():
        _print_finding(finding)

    stats = report.stats
    # Cached units are named rather than left out of the count: a second run
    # over unchanged code otherwise reports findings "from 0 chunk(s)", which
    # reads as a bug rather than as the cache doing its job.
    looked_at = stats.chunks_inspected + stats.chunks_cached
    reused = f", {stats.chunks_cached} reused" if stats.chunks_cached else ""
    print(
        f"{len(report.findings)} finding(s) from {looked_at} chunk(s){reused}. "
        f"{stats.candidates} candidate(s), {stats.refuted} refuted, "
        f"{stats.dropped_unlocatable} dropped as unlocatable."
    )
    print(f"report: run {run.run_id} in the database")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    source = Path(args.path).resolve()
    if not source.is_dir():
        _err(f"not a directory: {source}")
        return 2

    run = new_run()
    _load_tree(source, run)
    result = index_run(run)
    store = run.store()
    try:
        order = store.order()
    finally:
        store.close()

    print(f"run {run.run_id}: {json.dumps(result.as_dict())}")
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

    run = new_run(config)
    _load_tree(source, run)
    index_result = index_run(run)
    print(f"run {run.run_id}: indexed {index_result.files_indexed} files, {index_result.chunks} chunks")

    return _inspect_run(run, config, index_result.as_dict())


def cmd_runs(args: argparse.Namespace) -> int:
    runs = list_runs()
    if not runs:
        print("no runs")
        return 0
    for summary in runs:
        index = summary.get("index", {})
        print(f"{summary.get('run_id', '?')}  {summary.get('status', '?'):<12} {index.get('chunks', '?')} chunks")
    return 0


def cmd_corpus(args: argparse.Namespace) -> int:
    """Ingest or describe the corpus of known weaknesses. See `agent/rag/`.

    `ingest` runs from `scripts/up.sh` on every start, so it has to be cheap
    when nothing has changed: sample ids are content-derived, and an unchanged
    tree never constructs the embedder at all.
    """
    from .rag import corpus

    if args.action == "stats":
        rows = corpus.counts()
        if not rows:
            print("corpus is empty -- run 'agent corpus ingest'")
            return 0
        for cwe, variant, count in rows:
            print(f"{cwe:<10} {variant:<11} {count}")
        print(f"\n{sum(n for _, _, n in rows)} samples")
        return 0

    try:
        result = corpus.ingest(Path(args.path).resolve() if args.path else None)
    except corpus.Unavailable as err:
        # Not a failure to ingest: a failure to have the extra installed, which
        # is a different thing to tell somebody.
        print(f"corpus: {err}")
        return 1
    if result["embedded"] == 0 and result["removed"] == 0:
        print(f"corpus: {result['total']} samples, nothing new")
    else:
        print(
            f"corpus: {result['embedded']} embedded, {result['removed']} removed, "
            f"{result['total']} total"
        )
    if result["skipped"]:
        # Said out loud rather than swallowed: a file in a folder with no CWE in
        # its name is silently not in the corpus, and that is worth knowing.
        print(f"corpus: skipped {result['skipped']} file(s) with no CWE folder or no functions")
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
    """Read finished runs, propose, and replay. Never inside a request.

    `propose` and `list` only read. `replay` is the expensive one and the only
    one that changes what a proposal is allowed to become: it indexes a pinned
    corpus, inspects it twice -- once under each config -- and attaches the
    result. `apply` refuses without that.
    """
    from . import harness, replay as replay_module, tuner

    if args.action == "configs":
        for recorded in harness.all_configs():
            pin = " (pinned)" if recorded.pinned else ""
            print(f"{recorded.config_hash}{pin}  {recorded.label}")
        return 0

    if args.action == "list":
        found = tuner.proposals(status=args.status or "")
        if not found:
            print("no proposals")
            return 0
        for item in found:
            print(f"{item['id']}  {item['status']:<9} {item['base_hash']} -> {item['proposed_hash']}")
            print(f"    {item['evidence'].get('note', '')}")
        return 0

    if args.action == "propose":
        made = tuner.propose(args.config_hash)
        if not made:
            print("nothing to propose -- too few runs, a pinned config, or nothing worth changing")
            return 0
        for proposal in made:
            tuner.save(proposal)
            print(f"{proposal.id}  {proposal.changes}")
            print(f"    {proposal.evidence.note}")
        return 0

    if args.action == "replay":
        stored = [p for p in tuner.proposals() if p["id"] == args.proposal]
        if not stored:
            print(f"no such proposal: {args.proposal}")
            return 1
        proposal = stored[0]
        report = replay_module.compare(
            base_hash=proposal["base_hash"],
            proposed_hash=proposal["proposed_hash"],
            metric=proposal["metric"],
            direction=proposal["direction"],
            run_arm=_replay_arm,
            corpus=str(Path(args.corpus).resolve()),
        )
        tuner.attach_replay(args.proposal, report)
        moved = "improved" if report["improved"] else "did not improve"
        print(f"{report['metric']}: {report['before']:.4f} -> {report['after']:.4f} ({moved})")
        return 0 if report["improved"] else 1

    if args.action == "apply":
        try:
            applied = tuner.apply(args.proposal)
        except tuner.NotReplayed as err:
            print(f"refused: {err}")
            return 1
        print(f"applied {applied['id']}; config is now {applied['config_hash']}")
        return 0

    return 1


def _replay_arm(config: AgentConfig, corpus: str) -> Report:
    """One arm of an A/B: a whole inspection of the pinned corpus.

    Its own run each time. The replay exists because the change has not been
    observed yet, so anything reused from an earlier run is evidence about the
    config that produced it -- which is the config being replaced.

    ``warm=False`` for the sharper version of the same problem: the result cache
    is keyed by content and both arms read identical files, so the second arm
    would otherwise be served the first arm's answers and the comparison would
    be of a config against itself.
    """
    run = new_run()
    _load_tree(Path(corpus), run)
    index_run(run)

    store = run.store()
    try:
        return run_inspection(
            run_id=run.run_id,
            files=run.file_contents(),
            store=store,
            config=config,
            warm=False,
        )
    finally:
        store.close()


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

    corpus_parser = subparsers.add_parser("corpus", help="The corpus of known weaknesses")
    corpus_parser.add_argument("action", choices=("ingest", "stats"), nargs="?", default="ingest")
    corpus_parser.add_argument("path", nargs="?", help="Corpus directory (default: <root>/corpus)")
    corpus_parser.set_defaults(func=cmd_corpus)

    tune_parser = subparsers.add_parser("tune", help="Read finished runs and propose harness changes")
    tune_parser.add_argument("action", choices=("propose", "list", "configs", "replay", "apply"))
    tune_parser.add_argument("--config-hash", default="", help="Which harness to read runs of")
    tune_parser.add_argument("--proposal", default="", help="Which proposal to replay or apply")
    tune_parser.add_argument("--corpus", default="", help="Pinned corpus for the A/B replay")
    tune_parser.add_argument("--status", default="", help="Filter the list by status")
    tune_parser.set_defaults(func=cmd_tune)

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
