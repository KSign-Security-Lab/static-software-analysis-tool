# Static Software Analysis Tool (SSAT)

Static analysis of C/C++/Java source, built on [Joern](https://joern.io) Code
Property Graphs. Two analysis lines share one CPG front end:

- **F2-A** — OCPP-native evidence extraction. Asks the four CPG views
  (AST / CFG / DFG / CG) whether an untrusted OCPP payload field reaches a
  dangerous sink without adequate checks, and emits reviewable evidence.
- **Graph extraction** — CPG → Template → per-function AST and def-use DFG, in
  the JSON schema the GNN trainer in `packages/gnn` consumes.

## Layout

```
packages/ssat/          the analysis library and the `ssat` CLI
  src/ssat/
    cpg/                CPG generation: two backends behind one interface
    template/           CPG -> Template (KAST-style) conversion
    ast/                Template -> per-function AST
    dfg/                AST -> per-function def-use DFG
    knowledge/          shared C stdlib facts (sinks, allocators, bounds)
    pipeline/           stage orchestration + artifact writing
    f2a/                F2-A evidence extraction (self-contained)
    cli/                the `ssat` command
  tests/                pytest suite + golden snapshots
packages/gnn/           GNN training/evaluation over the extracted graphs
api/                    FastAPI service
web/                    Next.js UI
docs/v2/                F2-A design documents
artifacts/              generated output, scratch and corpora (gitignored)
```

Nothing in `artifacts/` is source — see `artifacts/README.md`. Delete any of it
and the repo still builds.

## Prerequisites

- Python 3.14+ and [uv](https://docs.astral.sh/uv/)
- A CPG backend, either:
  - **jpype** (default) — a local Joern install; point `JOERN_HOME` at its
    `joern-cli` directory. Runs in-process, no container.
  - **docker** — the bundled Joern image (`docker compose up -d`).
- Node 20+ for the web UI

## Quick start

```bash
uv sync                       # Python workspace
source .venv/bin/activate     # or prefix each command with `uv run`

ssat f2a  path/to/file.c      # OCPP evidence candidates
ssat full path/to/file.c      # AST + DFG per function
```

Output lands in `result/<mode>_<timestamp>/` unless you pass `-o`.

## CLI

One command, one subcommand per stage:

```
ssat cpg                 source        -> CPG (GraphSON)
ssat template            CPG           -> Template nodes
ssat ast                 CPG           -> per-function AST
ssat dfg                 CPG           -> per-function def-use DFG
ssat full                CPG           -> AST + DFG per function (GNN schema)
ssat template-functions  Template      -> one file per function
ssat f2a                 CPG           -> OCPP evidence candidates
```

The input path is positional. Every subcommand also takes `-o/--output` and
`--backend {jpype,docker}`; `--workers` parallelises CPG generation only.

## Web UI and API

```bash
scripts/dev-api.sh          # FastAPI on :8000 with auto-reload
cd web && npm run dev       # Next.js on :3000
```

The API exposes `/cpg-jpype`, `/cpg-docker`, `/template`, `/ast`, `/dfg`,
`/analyze-functions`, `/f2a`, `/analyze` and `/health`. `GET /health` reports
which CPG backends are usable on this host.

Note the UI derives AST/CFG/DFG/CG *views* from a CPG client-side, by edge
label. Those are a different thing from the `/ast` and `/dfg` endpoints, which
return the SSAT pipeline's own artifacts.

## Development

```bash
ruff check
ruff format --check
mypy
pytest

cd web && npm run type-check && npm run lint && npm run test
```

No path arguments: the targets live in `pyproject.toml`, so there is one
definition of what gets checked rather than one per caller.

That is exactly what CI runs — see `.github/workflows/ci.yml`, which invokes
the same commands directly rather than going through a task runner.

### Golden snapshots

`packages/ssat/tests/golden/` records the exact AST and DFG the pipeline
produces for every CPG fixture. They answer *"did this change?"*, never *"is
this correct?"* — a diff there is a regression unless the change was
deliberate, in which case rerun the generator and review the diff:

```bash
python packages/ssat/tests/generate_golden.py
```

## Notes

- **Two DFGs, one survivor.** The DFG here is a def-use analysis: it tracks
  memory reads and writes, buffer access, sink classification and guard bounds.
  An earlier second implementation only projected CPG `REF` edges — a filter,
  not an analysis — and has been removed.
- **Two CPG backends, same output.** `jpype` and `docker` run the same Joern.
  If they disagree, the two Joern versions differ; the container pins
  `JOERN_VERSION` in the `Dockerfile`, and
  `tests/test_cpg_backends.py::test_report_backend_skew` prints the delta.
- **F2-A is frozen.** See `docs/v2/f2a-milestone-status.md`. Its knowledge base
  (`ssat/f2a/kb.py`) is OCPP protocol semantics and is deliberately separate
  from `ssat/knowledge/`, which holds libc memory facts.
