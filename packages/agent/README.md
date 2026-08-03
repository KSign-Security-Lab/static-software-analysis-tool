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

Three steps: start a model server, point the agent at it, run it.

### 1. Start vLLM

**Install vLLM somewhere other than this project's venv.** It pulls in a pinned
torch/CUDA stack, this workspace is on Python 3.14, and vLLM does not
necessarily publish wheels that new. The agent only needs an HTTP endpoint, so
the two never have to share an environment.

Docker avoids the Python-version question entirely and is the easier path:

```bash
docker run --rm --gpus '"device=0"' \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-Coder-14B-Instruct \
  --served-model-name coder \
  --max-model-len 16384
```

Or in its own virtualenv:

```bash
python3.12 -m venv ~/.venvs/vllm && ~/.venvs/vllm/bin/pip install vllm
~/.venvs/vllm/bin/vllm serve Qwen/Qwen2.5-Coder-14B-Instruct \
  --served-model-name coder --max-model-len 16384
```

Either way the first run downloads the weights, which takes a while.

**Picking a model and a GPU layout.** A 14B at FP16 is about 28 GB of weights
and fits one 48 GB card with room for KV cache. A 32B at FP16 is roughly 64 GB
and needs either a 4-bit AWQ/GPTQ build (`--quantization awq`, about 18 GB) on
one card, or both cards via `--tensor-parallel-size 2`.

Both GPUs can be used together. Whether it is worth it depends on how they are
connected, so measure rather than assume — on this host `nvidia-smi topo -m`
reports `NODE` (PCIe through the host bridge, no NVLink) and
`torch.cuda.can_device_access_peer` is False both ways, so every tensor-parallel
all-reduce is staged through host memory. vLLM detects the missing peer access
and falls back off its custom all-reduce; pass `--disable-custom-all-reduce` if
it does not.

Two more consequences of these particular cards being different generations:

- **FP8 is unavailable.** It needs sm_89 (the RTX 6000 Ada); the A6000 is sm_86.
  BF16/FP16 and INT4 AWQ/GPTQ run on both.
- **The slower card sets the pace.** Tensor parallelism splits work evenly, so
  the result is roughly twice an A6000, not Ada plus Ada.

So tensor parallelism here buys *capacity*, not speed: it is what makes a 32B at
FP16 possible at all. If a quantised 32B is good enough, one card is the better
trade — no interconnect cost, and it can be the faster one
(`CUDA_VISIBLE_DEVICES=0`).

Running two independent single-GPU servers instead would buy nothing today. The
inspection loop is deliberately sequential — callees before callers, so notes
propagate — so it issues one request at a time and never has a second in flight.
That also keeps batch size at 1, which makes per-token all-reduce traffic small
and the missing NVLink less punishing than it would be for batch serving.
Inspecting chunks that share a topological level concurrently would change that,
and is the point at which a second server starts to pay.

`--max-model-len` has to clear the context-pack budget. `AGENT_CONTEXT_CHARS`
defaults to 24 000 characters, which is roughly 6–8k tokens of code, and the
prompt adds instructions on top — 16384 is a comfortable floor.

Check it is up and note the id it reports:

```bash
curl -s http://localhost:8000/v1/models | python3 -m json.tool
```

### 2. Point the agent at it

```bash
uv sync
source .venv/bin/activate

export AGENT_BASE_URL=http://localhost:8000/v1
export AGENT_MODEL=coder          # must match "id" from /v1/models
```

There is no default model. A wrong one produces confident nonsense that looks
like a working system, so an unset model fails at startup instead of at chunk
400 of 600.

Any OpenAI-compatible server works, not just vLLM — Ollama
(`AGENT_BASE_URL=http://localhost:11434/v1`) is handy for a quick local try,
though small quantised models vary a lot run to run.

### 3. Run it

```bash
# Deterministic and free: no model is called. Good first check.
agent index packages/ssat/tests/fixtures/f2a

# The real thing. -v logs each model call and every dropped anchor.
agent inspect -v packages/ssat/tests/fixtures/f2a

agent runs                        # previous runs and their status
```

Expect **minutes, not seconds** — one model call per chunk plus one per
candidate finding. Start with a handful of files.

Output looks like this, and the counts are deliberately not merged into a single
score:

```
run 9ecda9121fbb: indexed 1 files, 2 chunks
 ! fw.c:6:5: high [CWE-78] Command Injection
     sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
     "url" is interpolated into a shell command without sanitisation...
     fix: Build the command without a shell, or escape the input.
1 finding(s) from 2 chunk(s). 3 candidate(s), 0 refuted, 2 dropped as unlocatable.
```

`dropped as unlocatable` means the model described a finding but its quoted
source text could not be found in the file, so it was discarded rather than
pointed at a guessed line. A high number there means the prompt is drifting;
`-v` prints each rejected anchor.

### From the browser

```bash
scripts/dev-api.sh                # FastAPI on :8000 -- use a different port if
                                  # vLLM already has 8000
cd web && npm run dev             # Next.js on :3000
```

Open <http://localhost:3000/inspect>, upload a zip or a set of files, and press
**검사 실행**. Findings stream in as each chunk finishes and appear as squiggles;
click one for the explanation, evidence and proposed fix. If the banner says the
model is not configured, `AGENT_MODEL` was not set in the shell that started the
API.

> The API defaults to port 8000, which is also vLLM's default. Run vLLM on
> another port (`--port 8001`) or the API on one (`--port 8080`, then set
> `NEXT_PUBLIC_API_PORT`).

### MCP server on its own

The tool surface can be driven without the agent, e.g. from the MCP Inspector:

```bash
AGENT_RUN_ROOT=path/to/src agent-mcp        # stdio
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_BASE_URL` | `http://localhost:8000/v1` | OpenAI-compatible endpoint |
| `AGENT_MODEL` | *(none — required)* | Model id the endpoint serves |
| `AGENT_RUNS_DIR` | `artifacts/agent-runs` | Where run workspaces live |
| `AGENT_SANDBOX` | `bwrap` | `bwrap`, `docker` or `none` |
| `AGENT_CONTEXT_CHARS` | `24000` | Context-pack budget per chunk |
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
