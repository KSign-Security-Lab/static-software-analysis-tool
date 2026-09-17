# agent — chunk-by-chunk LLM code inspection

Reads a source tree one function at a time with an LLM, and returns findings
precise enough to render as lint markers in an editor.

```
 ! download.c:28:5: high [CWE-78] Command Injection
     sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
     "url" is interpolated into a shell command without sanitisation...
     fix: Build the command without a shell, or escape the input.
2 finding(s) from 13 chunk(s). 5 candidate(s), 1 refuted, 2 dropped as unlocatable.
```

## Quickstart

```bash
uv sync                                       # once
cp .env.example .env                          # model, GPUs, weights path
docker compose up -d --wait postgres
docker compose --profile vllm up -d --wait vllm

agent inspect path/to/src -v
```

`AGENT_MODEL` can stay unset — unset means ask the endpoint, and one served model
settles it. For the browser instead of the terminal, see [Running the UI](#running-the-ui).

## Architecture

### How the code is layered

```mermaid
graph TB
  subgraph D ["drivers — what starts a run"]
    direction LR
    CLI["cli"]:::m ~~~ API["api/agent"]:::m ~~~ BE["bench · tuner"]:::m
  end

  subgraph O ["orchestration — the only layer that touches both sides"]
    G["<b>graph/</b> — plan · context · triage · lenses · locate · gather · verify"]:::m
  end

  subgraph MID [" "]
    direction LR
    subgraph F ["facts about the code — no model, ever"]
      direction LR
      IX["index/<br/>chunks · links · order · reach"]:::m
      CX["context · locate<br/>tools · knowledge · rag"]:::m
    end
    subgraph M ["asking a model"]
      direction LR
      PR["prompts<br/>promptstore"]:::m
      LL["<b>llm</b><br/>the one place<br/>a model is called"]:::m
    end
  end

  subgraph B ["contract and storage"]
    direction LR
    SC["<b>schema</b><br/>what the model may say"]:::m ~~~ DB["db · runs<br/>Postgres"]:::m ~~~ CF["config"]:::m
  end

  D --> O
  O --> F
  O --> M
  F --> B
  M --> B

  classDef m fill:#eef,stroke:#88a
```

Dependencies point **down only**. That is checkable, not aspirational: on
module-level imports the package is a DAG, and the few cycles that would exist
are deliberately broken with in-function imports.

The split in the middle layer is the whole design. **Only `graph` and `remediate`
import `llm`** — `index`, `context`, `locate`, `tools`, `knowledge` and `rag`
cannot reach a model at all. So everything derived from the code is
deterministic, cacheable and testable without a GPU, while `schema` at the
bottom fixes what the model is allowed to say: it proposes a `ChunkAnalysis`,
never an id, a span or a verdict. The server owns those.

That one boundary explains most of the rest — why the model quotes source
instead of reporting line numbers, why reachability is computed but never shown
to it, and why two runs over one tree are comparable.

### What runs where

```mermaid
graph TB
  BR["<b>browser</b> — web, Next.js :4400"]
  TE["<b>terminal</b> — agent CLI"]

  BR -->|"HTTP + SSE"| API
  TE -->|"in process, no API"| LIB

  subgraph proc ["one process — the API server, or the CLI"]
    API["<b>api/agent</b> · FastAPI :4401<br/>runs · inspect · events · findings · patch"]
    WK["<b>worker thread</b> — one per run"]
    LIB["<b>packages/agent</b><br/>index · LangGraph loop · llm"]
    API --> WK --> LIB
  end

  LIB <-->|"OpenAI API, ≤ AGENT_MAX_INFLIGHT"| VL["<b>vLLM</b> :4403 — Qwen3.8-27B-FP8"]
  LIB <-->|"stdio"| MCP["<b>MCP server</b> — subprocess<br/>read · search · graph · corpus"]
  LIB <--> PG
  MCP --> PG
  CO["<b>corpus/</b> — 100 labelled CWE samples"] -->|"agent corpus ingest"| PG
  PG[("<b>Postgres + pgvector</b> :4402<br/>runs · files · chunks · links · notes · findings<br/>spans · checkpoints · vectors · corpus")]
```

`packages/agent` is a library, not a service. The API drives it from a worker
thread — one per run, streaming progress over SSE — and the CLI drives the same
library in its own process, with no API involved. Everything a run knows lives in
Postgres, so a browser tab can reattach to a run it did not start.

The agent is a **client of its own MCP server**: the tool surface is defined once
and served over stdio, so there is no in-process copy that could drift from what
an external client would see.

Nothing here imports `ssat` or `gnn` — the repo's structural-analysis route is
separate and shares only the database server.

## How it works

### ① A run, end to end

```mermaid
graph LR
  A["source tree<br/>125 files"] --> B["<b>index</b><br/>cut into functions,<br/>resolve the call graph<br/><i>no model calls</i>"]
  B --> C["<b>860 chunks</b><br/>ordered callees-first"]
  C --> D["<b>inspect</b><br/>one pipeline per chunk"]
  D --> E["<b>findings</b><br/>line span · evidence · patch"]
  D <-.->|"~4 calls per chunk<br/>~3,600 in all"| V["vLLM"]
```

The source tree never enters a prompt whole. It is cut into one chunk per
function, and each chunk gets its own small pipeline — one function plus the
context it needs, about 5,000 tokens. Indexing is deterministic; `inspect` is
the only phase that calls a model.

### ② How chunks are scheduled

```mermaid
gantt
    title A round runs its chunks at once; a chunk waits only for what it calls
    dateFormat X
    axisFormat %S
    tickInterval 1second
    section Round 1
    log_msg              :a1, 0, 2s
    parse_header         :a2, 0, 3s
    copy_field           :a3, 0, 5s
    section Round 2
    handle_request       :b1, after a3, 4s
```

A chunk waits for the functions it calls, and for nothing else. When a callee is
analysed the model leaves a one-line *note* — "returns a buffer built from
`req->location` with no validation" — and that note goes into every caller's
context, so taint crosses function boundaries without the whole call tree
entering one prompt.

Everything with no unfinished callees goes at once, up to `AGENT_WAVE_WIDTH`
(16). Widening a round cannot change the findings: every context pack in a round
is built before any of them runs, so two chunks going together never see each
other's notes. A test pins that.

### ③ Inside one chunk

```mermaid
graph LR
  A[triage] --> B[scout] --> C["specialists<br/><i>up to 5, in parallel</i>"] --> D[locate]
  D -->|per finding| E[gather] --> F[verify] --> G[reduce]
  D -.->|nothing found| G
```

| step | model calls | what it does |
| --- | --- | --- |
| `triage` | 1 | Is this worth expert time, and which experts? Biased to say yes. |
| `scout` | 0, unless the unit overflows the window | Which line ranges are worth reading. |
| specialists | 1–2 each, only the ones triage picked (1.6 on average) | One family of defect each — memory, injection, access, crypto, logic — told to leave the others alone. |
| `locate` | **0** | Resolves the model's quoted `anchor_text` to a real line span. No match, the finding is dropped. |
| `gather` | ≤4 per finding | Looks things up with MCP tools before ruling — including the two retrieval ones. |
| `verify` | 1 per finding | Tries to *refute* the claim. Uncertain counts as refuted. |
| `reduce` | 0 | Writes what survived; marks the chunk inspected. |

### What the model can look up

Context packs are assembled from the call graph, deterministically — nothing is
retrieved into a prompt behind the model's back. Retrieval is a *tool it chooses
to call*, and only where a claim is being judged:

| tool | index | answers |
| --- | --- | --- |
| `search_corpus` | 100 labelled samples in [`corpus/`](../../corpus) — 10 CWE classes as vulnerable/fixed pairs, embedded with `jina-embeddings-v2-base-code` | "what recorded weakness does this code resemble?" Right CWE came back first on 8 of 10 held-out functions. |
| `search_semantic` | this run's own chunks, embedded with `bge-small-en-v1.5` | "is there a check on this anywhere?" — when you cannot guess the identifier |
| `graph_path`, `graph_neighbours`, `graph_subsystem` | the call graph, via [graphify](../graphify/README.md) | what actually reaches what |
| `find_callers`, `find_definition`, `read_source`, `search_text` | the index | exact lookups by name |

Both vector stores need the optional extra — `uv sync --extra rag` — and
`agent corpus ingest` to populate the first. Without it those two tools say so
and the run continues.

Resemblance is not reachability: `search_corpus` is a strong hint about *which
class* of weakness this is, and no evidence that the code is reachable or
exploitable.

`GET /agent/graph` publishes ② and ③ from the compiled graph, not from this page.

**Why it is built this way** — syntactic chunks, five narrow analysts, why the
server locates spans instead of trusting line numbers, reachability labelling:
[docs/design.md](docs/design.md).

## CLI

```bash
export AGENT_BASE_URL=http://localhost:4403/v1

agent index   path/to/src         # deterministic, no model calls
agent inspect path/to/src -v      # the real thing
agent runs                        # previous runs
agent endpoints                   # what is reachable, and what it serves
agent bench ...                   # SEC-bench — docs/operating.md
agent tune  ...                   # propose, replay and apply config changes
```

### Running the UI

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 4401 \
  --reload --timeout-graceful-shutdown 2 \
  --reload-dir api --reload-dir packages/ssat/src/ssat \
  --reload-dir packages/agent/src/agent --reload-dir packages/graphify/src/graphify
cd web && pnpm dev                # Next.js on :4400
```

Open <http://localhost:4400/agent>, upload a zip or a set of files, and press
검사 실행. Findings stream in as each chunk finishes; click one for the
explanation, evidence and proposed fix. The `AGENT_*` variables have to be set in
the shell that starts the API, and the banner says so if they are not.

## Configuration

Read from the environment or `.env`, which Compose reads too.

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_BASE_URL` | `http://localhost:4403/v1` | OpenAI-compatible endpoint |
| `AGENT_MODEL` | *(the endpoint's, when it serves one)* | Model id the endpoint serves |
| `AGENT_DATABASE_URL` | `postgresql+psycopg://ssat:ssat@localhost:4402/ssat` | Where runs live |
| `AGENT_CONTEXT_CHARS` | `24000` | Context-pack budget per chunk |
| `AGENT_MAX_TOKENS` | `4096` | Ceiling on one response; bounds a model that cannot finish the schema |
| `AGENT_MAX_VERIFY_PER_CHUNK` | `8` | Cap on refute calls per chunk |
| `AGENT_TOOLS` | `1` | Let verification call MCP tools; `0` disables |
| `AGENT_MAX_TOOL_CALLS` | `4` | Tool calls allowed per finding |
| `AGENT_WAVE_WIDTH` | `16` | Chunks dispatched per round, all dependency-ready |
| `AGENT_MAX_CONCURRENCY` | `16` | Graph tasks run at once |
| `AGENT_MAX_INFLIGHT` | `16` | Ceiling on requests actually in flight — size it to the endpoint |
| `AGENT_LENSES` | *(all five)* | Comma-separated: `memory,injection,access,crypto,logic` |
| `AGENT_TRIAGE` | `1` | Screen each chunk before the specialists; `0` runs them all |
| `AGENT_ENTRY_POINTS` | *(none)* | Symbol globs that are entry points whatever the call graph says, e.g. `handle_*` |

The endpoint's own settings — model, GPUs, parsers, KV budget — are in
[docs/serving.md](docs/serving.md).

## Layout

```
src/agent/
  languages.py     per-grammar node names, one table
  index/
    chunk.py       tree-sitter -> chunks
    links.py       symbol resolution -> edges
    order.py       topological order, call depth, dependencies, ready rounds
    reach.py       whether a unit is reached, from the same call graph
    store.py       chunks, links, notes, findings, scoped to one run
  schema.py        the contract: model-facing and wire schemas
  schema_ts.py     generates web/lib/agent-schema.ts
  locate.py        anchor_text -> real span, or nothing
  context.py       context packs, assembled from the index
  prompts.py       triage, the five specialists, and the refute prompt
  promptstore.py   prompts tuned against a trace, read at run time
  llm.py           the one place a model is called
  graph/           LangGraph nodes, fan-out and wiring
  knowledge.py     the index as a graphify knowledge graph
  mcp/             the tool surface over MCP
  tools.py         tool implementations (read, grep, graph)
  db/              the schema: one row per run, everything cascading
  runs.py          the run handle over that schema
  files.py         upload validation and hostile-archive caps
  cli.py           the `agent` command
```

## More

| | |
| --- | --- |
| [docs/design.md](docs/design.md) | Why it is built this way, and what will bite you |
| [docs/serving.md](docs/serving.md) | vLLM settings, verified models, GPU layout |
| [docs/operating.md](docs/operating.md) | Testing, MCP tools, LangSmith, SEC-bench |
