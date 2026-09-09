# Static Software Analysis Tool (SSAT)

Static analysis of source code by two independent routes.

**Structural**, built on [Joern](https://joern.io) Code Property Graphs. Two
lines share one CPG front end:

- **F2-A** — OCPP-native evidence extraction. Asks the four CPG views
  (AST / CFG / DFG / CG) whether an untrusted OCPP payload field reaches a
  dangerous sink without adequate checks, and emits reviewable evidence.
- **Graph extraction** — CPG → Template → per-function AST and def-use DFG, in
  the JSON schema the GNN trainer in `packages/gnn` consumes.

**LLM-based**, in `packages/agent`: a model reads the code one syntactic chunk
at a time, with callees analysed before their callers so what a callee does to
its inputs is known by the time its caller is judged. Findings carry resolved
line-level spans, so each one can show the code it is about, the evidence trail
behind it, and a patch for exactly those lines.

The two routes coexist and neither depends on the other — `agent` imports
neither `ssat` nor `gnn`.

## Layout

```
packages/ssat/          the analysis library and the `ssat` CLI
  src/ssat/
    cpg/                CPG generation: Joern in this process, via JPype
    template/           CPG -> Template (KAST-style) conversion
    ast/                Template -> per-function AST
    dfg/                AST -> per-function def-use DFG
    knowledge/          shared C stdlib facts (sinks, allocators, bounds)
    pipeline/           stage orchestration + artifact writing
    f2a/                F2-A evidence extraction (self-contained)
    cli/                the `ssat` command
  tests/                pytest suite + golden snapshots
packages/gnn/           GNN training/evaluation over the extracted graphs
packages/agent/         LLM inspection over an OpenAI-compatible endpoint
  src/agent/
    index/              tree-sitter chunking, link resolution, chunk store
    graph/              the LangGraph inspection loop
    mcp/                the tool surface, served over MCP
api/                    FastAPI service (SSAT routes + /agent/*)
web/                    Next.js UI — five surfaces, two shells:
                          /agent           검사: upload, scan, triage, patch
                          /f2a             F2-A evidence over a CPG
                          /extract         AST / CFG / DFG / call graph views
                          /extract/stages  run one pipeline stage, read raw JSON
                          /bench           public-benchmark results
docs/v2/                F2-A design documents
artifacts/              generated output, scratch and corpora (gitignored)
```

Nothing in `artifacts/` is source — see `artifacts/README.md`. Delete any of it
and the repo still builds.

## Prerequisites

- Python 3.14+ and [uv](https://docs.astral.sh/uv/)
- A local **Joern** install and a **JDK** — Joern's JARs run in this process
  via JPype. Point `JOERN_HOME` at the `joern-cli` directory (it defaults to
  `/usr/bin/joern/joern-cli`). There is no container alternative any more.
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

The input path is positional. Every subcommand also takes `-o/--output`;
`--workers` parallelises CPG generation only.

Joern runs in the process that asks for it, JARs loaded through JPype, so no
container is involved anywhere. `ssat cpg` over a directory is a process pool
and each worker starts its own JVM — one JVM cannot be shared across processes
— so `--workers 4` means four of them, and the memory to match. Without JARs to
load the command stops before doing any work and says to set `JOERN_HOME`.

The agent is a separate line of analysis and uses neither Joern nor a JVM: it
parses with tree-sitter and needs only Postgres.

The five stages that build a Template also take `--no-replace-macro`. Joern runs
no preprocessor: it models a `#define` as a function and each use of it as a
call, inlining the expansion beneath the use site. By default that pseudo-call
is folded into its expansion, so `if (len < MAX)` carries a real bound and a
macro-wrapped `strcpy` is attributed to `strcpy`. The flag leaves the
pseudo-call in place, which is the shape templates written before this produced.

## Web UI and API

```bash
# The API on :8001. --reload-dir and --timeout-graceful-shutdown are both
# load-bearing; api/README.md says why.
uv run uvicorn api.main:app --host 0.0.0.0 --port 8001 \
  --reload --timeout-graceful-shutdown 2 \
  --reload-dir api --reload-dir packages/ssat/src/ssat \
  --reload-dir packages/agent/src/agent --reload-dir packages/graphify/src/graphify

cd web && pnpm dev          # Next.js on :3000
```

The API exposes `/cpg-jpype`, `/template`, `/ast`, `/dfg`,
`/analyze-functions`, `/f2a`, `/analyze` and `/health`. `GET /health` reports
whether Joern can run on this host.

Note the UI derives AST/CFG/DFG/CG *views* from a CPG client-side, by edge
label. Those are a different thing from the `/ast` and `/dfg` endpoints, which
return the SSAT pipeline's own artifacts.

## LLM inspection

```bash
uv sync && (cd web && pnpm install)                # once
cp .env.example .env                               # which model, which GPUs, where the weights go
docker compose --profile vllm up -d --wait vllm    # the model server, on :8000
docker compose up -d --wait postgres               # the run database
agent corpus ingest                                # the corpus of known weaknesses
```

`agent corpus ingest` embeds `corpus/` into Postgres so `search_corpus` has
something to answer with. Run it after a checkout and after editing the corpus;
sample ids are content-derived, so an unchanged corpus costs one query and never
loads the embedding model.

Which weights, which tool-call and reasoning parser, which GPUs and where the
cache lives are the `VLLM_*` variables in `.env`; Compose reads that file
itself. `--wait` blocks until the server answers, which on a cold cache is a
download.

`AGENT_MODEL` does not have to be set: unset means ask the endpoint, and the
served id — whatever `--served-model-name` chose — is the only right answer.
Set it explicitly when one server serves several models.

```bash
agent endpoints                  # what is reachable, and what it serves
agent index   path/to/src        # deterministic, no model calls
agent inspect path/to/src -v     # the real thing; minutes, not seconds
```

Or open `/agent` in the web UI — 검사. Give it a folder, a `.zip` or a git URL,
press 검사 시작, and findings stream in as they are found: severity, CWE, the
code, the evidence trail, how to fix it, and a patch for those exact lines. Tick
the ones that matter and the bucket becomes a unified `.patch`, a patched source
`.zip`, or -- for a run cloned from a repository -- a pushed branch.

Nothing is applied to the analysed tree, ever. That is what makes a finding's
anchor still mean something afterwards and a patch reproducible; the fix leaves
as a diff and is applied wherever the reader chooses.

Backed by `/agent/runs`, `/agent/runs/git`, and
`/agent/runs/{id}/{files,file,inspect,events,findings,propose,patch,archive,push}`.
Progress streams over SSE because a chunk-by-chunk run takes minutes.

Model choice, GPU sizing, port conflicts and how to read the output are in
[`packages/agent/README.md`](packages/agent/README.md).

## Development

There is no task runner and no wrapper script. Every command below is the real
one, so what you run locally is what CI runs and what this file can be checked
against.

```bash
ruff check
ruff format --check
mypy
pytest

cd web && pnpm type-check && pnpm lint && pnpm test
```

No path arguments: the targets live in `pyproject.toml`, so there is one
definition of what gets checked rather than one per caller. That is exactly what
CI runs — see `.github/workflows/ci.yml`.

The containers, by name — `vllm` and `secbench` are profile-gated, and Compose
silently matches nothing if the profile is left off:

```bash
docker compose ps -a                                     # what is up
docker compose up -d --wait postgres                     # start
docker compose --profile vllm up -d --wait vllm
docker compose --profile vllm logs -f --tail 200 vllm    # follow one
docker compose stop vllm                                 # stop, keep it
docker compose --profile vllm rm -sf vllm                # remove the container
```

Removing a container is safe: stored runs live in a named volume, the weights in
`HF_HOME`, and SEC-bench's images in its own daemon's data root. None of the
three goes with the container.

The other things worth knowing about:

```bash
python -m agent.schema_ts --write && python -m ssat.schema_ts --write
agent inspect -v packages/agent/tests/fixtures/sample
agent bench sweep
```

The first regenerates `web/lib/agent-schema.ts` from the pydantic wire models
and a test fails on drift. The second is the end-to-end check that a model
server, the database and the graph all work. The third is the unattended
SEC-bench sweep — see `packages/agent/README.md`.

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
- **One CPG engine, in this process.** There was a second that ran `docker
  exec` into a Joern container, which meant a second Joern to keep in step with
  the first — and they had drifted, 4.0.377 locally against the container's
  pinned 4.0.361. The container, the `/cpg-docker` endpoint, the `--backend`
  flag and the test that measured the skew are all gone. The cost is that a
  host with no local Joern can no longer generate a CPG.
- **F2-A is frozen.** See `docs/v2/f2a-milestone-status.md`. Its knowledge base
  (`ssat/f2a/kb.py`) is OCPP protocol semantics and is deliberately separate
  from `ssat/knowledge/`, which holds libc memory facts.
- **The agent locates findings by quoting, not by line number.** Models get line
  numbers wrong, so a finding names the offending source text and the server
  finds it. If it cannot be found, the finding is dropped rather than pointed at
  a guessed line.
- **The generated `web/lib/agent-schema.ts` is not hand-edited.** It comes from
  the pydantic wire models via `python -m agent.schema_ts --write`, and a test
  fails if the two drift.
