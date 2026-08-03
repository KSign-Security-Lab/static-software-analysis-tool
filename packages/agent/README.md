# agent — chunk-by-chunk LLM code inspection

Inspects a source tree one syntactic unit at a time using an LLM behind an
OpenAI-compatible endpoint (vLLM), and returns findings precise enough to render
as lint markers in an editor.

This is a **second, independent line of analysis**. It does not import `ssat` or
`gnn`, does not consume F2-A evidence, and does not replace the CPG pipeline —
the two coexist.

## How it works

```
source tree
   │
   ▼  tree-sitter
chunks ── one per function/method, plus one per file for the top-level
   │      material (includes, globals, struct and typedef definitions)
   ▼  symbol resolution (not embeddings)
links  ── calls / uses_type / file_depends
   │
   ▼  topological sort, callees first
inspection loop, one chunk at a time:
   plan → context → analyse → locate → verify
```

Three decisions do most of the work.

**Chunks are syntactic, not fixed windows.** A fixed window cuts functions in
half and destroys the only unit worth reasoning about.

**Callees are analysed before their callers.** When a callee is analysed the
model writes a *note* — "returns a buffer built from `req->location` with no
validation" — and that note is injected into every caller's context. Taint
crosses chunk boundaries without the whole tree ever entering one prompt. This
is what the cross-chunk metadata is for.

**The model quotes source; the server locates it.** Models get line numbers
wrong, so a finding carries `anchor_text` — the exact offending text — and
`agent.locate` derives the real line and column by finding it. Anchors come back
mangled in practice, so matching walks a ladder from exact to
whitespace-flexible. If no rung matches, **the finding is dropped**: a marker on
the wrong line is worse than no marker.

Two mangled forms in that ladder are not hypothetical — both were produced by a
served model during development:

| Model returned | Source actually says | Rung |
| --- | --- | --- |
| `"snprintf(cmd, \"wget %s\", loc);"` | `snprintf(cmd, "wget %s", loc);` | `dequoted` |
| `"wget %s", url;` | `sprintf(cmd, "wget %s", url);` | `punctuation-trimmed` |

The first is a correct finding that a naive substring test would have thrown
away. The second is the model completing a fragment into a statement; trimming
the punctuation it added leaves something that is still an *exact* substring, so
it is recovered without loosening the match.

## Quickstart

```bash
scripts/vllm.sh      # start a model server: pick a model and a GPU layout
agent                # run an inspection: pick an endpoint, model and target
```

`scripts/vllm.sh` runs vLLM in Docker. The host install is not used: it is
vllm 0.17 against torch 2.4, which predates `torch.library.infer_schema`, and
this workspace is on Python 3.14, which vLLM does not publish wheels for. The
agent only needs an HTTP endpoint, so the two never have to share a runtime.

Run it with no arguments and it shows the GPUs, offers a model catalogue
annotated with what actually fits, asks for a GPU layout, checks the model id
against the Hugging Face API before starting a multi-gigabyte download, and
waits until the server answers. Every prompt is also a flag:

```bash
scripts/vllm.sh start --model Qwen/Qwen2.5-Coder-32B-Instruct-AWQ --gpus 0
scripts/vllm.sh start --model Qwen/Qwen2.5-Coder-32B-Instruct --gpus 0,1   # tensor parallel
scripts/vllm.sh status
scripts/vllm.sh logs -f
scripts/vllm.sh stop
```

It serves on 8001, because the SSAT API already owns 8000.

`agent` with no arguments then finds the server, asks what it serves, and sets
`AGENT_BASE_URL` and `AGENT_MODEL` from the answer -- passing the Hugging Face
path where the served id belongs is the usual first failure, and this removes
the chance to make it. It indexes before offering to inspect, so the chunk count
is known before any of the run is paid for.

There is deliberately no shell wrapper around this. The CLI and the HTTP API are
two thin front ends over one library (`api` imports `agent`, never the reverse);
a third entry point in shell would duplicate endpoint discovery and model
selection outside the type, lint and test gate. `scripts/vllm.sh` stays a script
because it manages an external process and duplicates nothing.

### Doing it by hand

```bash
export AGENT_BASE_URL=http://localhost:8001/v1
export AGENT_MODEL=agent          # must match `curl $AGENT_BASE_URL/models`

agent index   path/to/src         # deterministic, no model calls
agent inspect path/to/src -v      # the real thing
agent runs                        # previous runs
```

### Choosing a model

Guided decoding guarantees the output *matches* the schema, not that the model
ever finishes it. A model too small for `ChunkAnalysis` emits a valid-so-far
prefix until it runs out of room -- measured on a 0.5B, which spent 8048 tokens
without closing the object. `AGENT_MAX_TOKENS` (default 4096) bounds that into a
fast, legible failure rather than a slow one, and the log says which model is at
fault.

Treat anything below about 7B as non-viable for this schema. A 4-bit 32B is the
sweet spot on a 48 GB card.

### GPU layout

Both GPUs can be used together — `scripts/vllm.sh` offers it, and
`--gpus 0,1` sets `--tensor-parallel-size 2`. Whether it is worth it depends on
how the cards are wired, so measure rather than assume:

```bash
nvidia-smi topo -m                      # NV# means NVLink; NODE means PCIe only
python -c "import torch; print(torch.cuda.can_device_access_peer(0,1))"
```

On this host that reports `NODE` and `False`, so every tensor-parallel
all-reduce is staged through host memory. The script passes
`--disable-custom-all-reduce` when it sees no NVLink, because vLLM's custom
all-reduce needs peer access.

Two more consequences when the cards are different generations, as they are
here (sm_89 Ada and sm_86 Ampere):

- **FP8 is unavailable.** It needs sm_89; the A6000 is sm_86. BF16/FP16 and
  INT4 AWQ/GPTQ run on both.
- **The slower card sets the pace.** Tensor parallelism splits work evenly, so
  the result is roughly twice an A6000, not Ada plus Ada.

So tensor parallelism here buys *capacity*, not speed: it is what makes a 32B at
FP16 possible at all. If a 4-bit 32B is good enough, one card is the better
trade — no interconnect cost, and it can be the faster one.

Running two independent single-GPU servers would buy nothing today. The
inspection loop is deliberately sequential — callees before callers, so notes
propagate — so it issues one request at a time and never has a second in flight.
That also keeps batch size at 1, which makes per-token all-reduce traffic small
and the missing NVLink less punishing than it would be for batch serving.
Inspecting chunks that share a topological level concurrently would change that,
and is the point at which a second server starts to pay.

### Reading the output

```
run 9ecda9121fbb: indexed 1 files, 2 chunks
 ! fw.c:6:5: high [CWE-78] Command Injection
     sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
     "url" is interpolated into a shell command without sanitisation...
     fix: Build the command without a shell, or escape the input.
1 finding(s) from 2 chunk(s). 3 candidate(s), 0 refuted, 2 dropped as unlocatable.
```

The counts are deliberately not merged into one number. `dropped as
unlocatable` means the model described a finding whose quoted source could not
be found in the file, so it was discarded rather than pointed at a guessed
line -- a small model will often produce prose there instead of code. A high
count means the prompt is drifting; `-v` prints every rejected anchor.

### From the browser

```bash
scripts/dev-api.sh                # FastAPI on :8000
cd web && npm run dev             # Next.js on :3000
```

Open <http://localhost:3000/inspect>, upload a zip or a set of files, and press
검사 실행. Findings stream in as each chunk finishes; click one for the
explanation, evidence and proposed fix. The `AGENT_*` variables have to be set
in the shell that starts the API, and the banner says so if they are not.

### MCP server on its own

The tool surface can be driven without the agent, e.g. from the MCP Inspector:

```bash
AGENT_RUN_ROOT=path/to/src agent-mcp        # stdio
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_BASE_URL` | `http://localhost:8000/v1` | OpenAI-compatible endpoint (`scripts/vllm.sh` serves on 8001) |
| `AGENT_MODEL` | *(none — required)* | Model id the endpoint serves |
| `AGENT_RUNS_DIR` | `artifacts/agent-runs` | Where run workspaces live |
| `AGENT_SANDBOX` | `bwrap` | `bwrap`, `docker` or `none` |
| `AGENT_CONTEXT_CHARS` | `24000` | Context-pack budget per chunk |
| `AGENT_MAX_TOKENS` | `4096` | Ceiling on one response; bounds a model that cannot finish the schema |
| `AGENT_MAX_VERIFY_PER_CHUNK` | `8` | Cap on refute calls per chunk |

## Layout

```
src/agent/
  languages.py     per-grammar node names, one table
  index/
    chunk.py       tree-sitter -> chunks
    links.py       symbol resolution -> edges
    order.py       topological order, cycle breaking
    store.py       per-run SQLite: chunks, links, notes, findings
  schema.py        the contract: model-facing and wire schemas
  schema_ts.py     generates web/lib/agent-schema.ts
  locate.py        anchor_text -> real span, or nothing
  context.py       context packs, assembled from the index
  prompts.py       analyse and refute prompts
  llm.py           the one place a model is called
  graph/           LangGraph nodes and wiring
  mcp/             the tool surface over MCP
  tools.py         tool implementations (fs, grep, graph, sandbox)
  runs.py          run workspaces, safe upload extraction
  cli.py           the `agent` command
```

## Notes

- **`mcp` is pinned below 2.0.** `langchain-mcp-adapters` 0.3.1 declares
  `mcp>=1.24.0` with no upper bound, so 2.0 installs and then fails at import:
  the adapter does `from mcp.server.fastmcp.tools import Tool`, and 2.0 removed
  that whole package. Revisit when the adapter ships a 2.x release.
- **Two schemas, kept apart.** The model is constrained to `ChunkAnalysis` and
  never asked to invent an id, a span, or a verdict; the server owns those. The
  TypeScript is generated from the wire models, with a test that fails on drift
  — regenerate with `python -m agent.schema_ts --write`.
- **Finding ids are content-derived**, keyed on the enclosing symbol rather than
  a line number. Editing code above a finding does not make it look new, which
  is what makes the run-to-run diff meaningful, and what makes re-inspection
  skip unchanged chunks.
- **Verification defaults against the finding.** A missing or uncertain verdict
  refutes. Past the per-chunk cap a finding is kept but flagged
  `verified: false` — silently dropping it would hide real findings and silently
  blessing it would launder unverified ones.
- **Nothing applies a fix.** `Remediation.diff` is display-only and there is no
  write endpoint. That is the seam a future "fix now" would attach to.
