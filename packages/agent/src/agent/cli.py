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
SAMPLE_TREE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sample"
LARGE_RUN_CHUNKS = 40


def _err(message: str) -> None:
    print(f"\033[31merror:\033[0m {message}", file=sys.stderr)


def _info(message: str) -> None:
    print(f"\033[36m{message}\033[0m")


def _load_tree(source: Path, run: Run) -> int:
    files: dict[str, bytes] = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        files[path.relative_to(source).as_posix()] = path.read_bytes()

    tree = write_files(run, files)
    for each in tree.skipped:
        _info(f"skipped {each.path} ({each.size / 1024 / 1024:.0f} MB): larger than one file may be")
    return len(tree.files)


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


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def _choose(prompt: str, options: list[str]) -> int:
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
    endpoints = discover()
    if not endpoints:
        return None
    labels = [f"{e.base_url}  ({', '.join(e.models[:3])})" for e in endpoints]
    print()
    _info("Endpoints")
    return endpoints[_choose("Endpoint", labels)]


def _interactive(config: AgentConfig) -> int:
    _info("SSAT agent")

    endpoint = _pick_endpoint()
    if endpoint is None:
        _err("no vLLM server is answering on port 8000 or 8001.")
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


def _inspect_run(run: Run, config: AgentConfig, index_stats: dict[str, int]) -> int:
    def emit(event: str, payload: object) -> None:
        if event == "chunk_finished" and isinstance(payload, dict):
            stats = payload.get("stats", {})
            done = stats.get("chunks_inspected", 0)
            total = stats.get("chunks_total", 0)
            found = len(payload.get("findings", []))
            suffix = f"  +{found}" if found else ""
            print(f"\r  [{done}/{total}] {str(payload.get('symbol', ''))[:40]}{suffix}", end="", flush=True)

    store = run.store()
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
        reach = store.reach()
        chunks = {c.chunk_id: c for c in store.chunks()}
    finally:
        store.close()

    print(f"run {run.run_id}: {json.dumps(result.as_dict())}")
    print(f"inspection order: {len(order)} chunks (callees before callers)")

    if reach:
        tally: dict[str, int] = {}
        for entry in reach.values():
            state = str(entry.get("state", "unknown"))
            tally[state] = tally.get(state, 0) + 1
        summary = "  ".join(f"{state} {count}" for state, count in sorted(tally.items()))
        print(f"reach: {summary}")
        for chunk_id, entry in sorted(reach.items(), key=lambda kv: str(kv[1].get("state"))):
            if entry.get("state") not in {"unreachable", "unknown"}:
                continue
            chunk = chunks.get(chunk_id)
            if chunk is None:
                continue
            why = " · ".join(str(reason) for reason in entry.get("why") or ())
            print(f"  {entry['state']:12} {chunk.file}:{chunk.start_line} {chunk.symbol}  ({why})")
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
        print(f"corpus: {err}")
        return 1
    if result["embedded"] == 0 and result["removed"] == 0:
        print(f"corpus: {result['total']} samples, nothing new")
    else:
        print(f"corpus: {result['embedded']} embedded, {result['removed']} removed, {result['total']} total")
    if result["skipped"]:
        print(f"corpus: skipped {result['skipped']} file(s) with no CWE folder or no functions")
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
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
    run = new_run()
    _load_tree(Path(corpus), run)
    index_run(run)

    store = run.store()
    try:
        report = run_inspection(
            run_id=run.run_id,
            files=run.file_contents(),
            store=store,
            config=config,
            warm=False,
        )
    finally:
        store.close()

    run.set_status(STATUS_DONE, replay=True)
    return report


def cmd_bench(args: argparse.Namespace) -> int:
    from .bench import dataset as ds
    from .bench.config import BenchConfig, load_env
    from .bench import runner as bench_runner
    from .bench import score as bench_score

    load_env()
    config = BenchConfig()

    if args.action == "sweep":
        from .bench.sweep import sweep as run_sweep

        return run_sweep(config, lambda action: cmd_bench(argparse.Namespace(action=action)))

    if args.action == "status":
        for key, value in config.describe().items():
            print(f"  {key:16s} {value}")
        if config.dataset_file.exists():
            print(f"\n  dataset          {sum(1 for _ in config.dataset_file.open())} instances")
        else:
            print("\n  dataset          not fetched -- run `agent bench fetch`")
        attempts = bench_runner.load_attempts(config)
        print(f"  attempts         {len(attempts)}")
        return 0

    if args.action == "fetch":
        counts = ds.fetch(config)
        for split, n in counts.items():
            print(f"  eval-{split}.jsonl  {n} instances -> {config.data_dir}")
        return 0

    chosen = ds.select(ds.load(config), config)
    if not chosen:
        _err("nothing selected")
        return 2

    if args.action == "prepare":
        ok = sum(1 for instance in chosen if bench_runner.prepare(instance, config))
        print(f"  {ok}/{len(chosen)} images ready")
        return 0 if ok == len(chosen) else 1

    if args.action == "run":
        print(f"  {len(chosen)} instance(s); each is a pull, an inspection and a patch")
        attempts = bench_runner.sweep(chosen, config, resume=config.resume)
        produced = sum(1 for a in attempts if a.patch)
        print(f"  {produced}/{len(attempts)} produced a patch -> {config.predictions_file}")
        return 0

    if args.action == "score":
        attempts = bench_runner.load_attempts(config)
        if not attempts:
            _err("no attempts to score -- run `agent bench run` first")
            return 2
        verdicts = bench_score.score(attempts, config)
        counts: dict[str, int] = {}
        for attempt in attempts:
            outcome, _ = bench_score.outcome_for(attempt, verdicts.get(attempt.instance_id))
            counts[outcome] = counts.get(outcome, 0) + 1
        for outcome, n in sorted(counts.items()):
            print(f"  {outcome:20s} {n}")
        return 0

    return 1


def cmd_endpoints(args: argparse.Namespace) -> int:
    endpoints = discover()
    for endpoint in endpoints:
        print(endpoint.base_url)
        for model in endpoint.models:
            print(f"  {model}")
    if not endpoints:
        print("no vLLM server answering on port 8000 or 8001")
        print("start one with: docker compose --profile vllm up -d --wait vllm")

    trace = tracing_status()
    print()
    print(f"langsmith: {'on -> ' + trace['project'] if trace['enabled'] else 'off'}")
    if trace["detail"]:
        print(f"  {trace['detail']}")
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

    bench_parser = subparsers.add_parser("bench", help="The SEC-bench sweep (offline)")
    bench_parser.add_argument("action", choices=("status", "fetch", "prepare", "run", "score", "sweep"))
    bench_parser.set_defaults(func=cmd_bench)

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
