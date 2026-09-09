# agent — chunk-by-chunk LLM code inspection

Inspects a source tree one syntactic unit at a time using an LLM behind an
OpenAI-compatible endpoint (vLLM), and returns findings precise enough to render
as lint markers in an editor.

A standalone package. It does not import `ssat` or `gnn`, and nothing in the
repo's structural analysis line feeds it or is fed by it — the two coexist.

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
   ▼  topological sort, callees first; call depth per chunk
inspection loop, one wave of independent chunks at a time:
   plan → context → triage → scout ─┬→ memory    ─┐
                                    ├→ injection ─┤
                                    ├→ access    ─┼→ locate → gather → verify → reduce
                                    └→ logic     ─┘
```

Four decisions do most of the work.

**Chunks are syntactic, not fixed windows.** A fixed window cuts functions in
half and destroys the only unit worth reasoning about.

**Callees are analysed before their callers.** When a callee is analysed the
model writes a *note* — "returns a buffer built from `req->location` with no
validation" — and that note is injected into every caller's context. Taint
crosses chunk boundaries without the whole tree ever entering one prompt. This
is what the cross-chunk metadata is for.

**Five narrow analysts, not one broad one.** A single prompt asked to hold
memory safety, injection, access control, cryptographic use and resource
lifetime in mind at once skims all five. Each specialist gets one family of
defect, is told to leave the others alone, and runs at the same time as its
peers — so recall goes up and the wall clock does not. A cheap screening call in
front of them decides which of the five a unit has earned; it is biased to say yes, because a false positive
there costs one analysis and a false negative loses a vulnerability. Chunks that
share a call depth cannot need each other's notes, so a *wave* of them goes at
once. `AGENT_WAVE_WIDTH`, `AGENT_MAX_CONCURRENCY`, `AGENT_LENSES` and
`AGENT_TRIAGE` are the levers; `AGENT_TRIAGE=0 AGENT_WAVE_WIDTH=1
AGENT_LENSES=injection` is close to what this used to do.

On the sample tree (13 chunks, one A6000-class card behind vLLM):

| Configuration | Model calls | Wall clock |
| --- | --- | --- |
| One lens, one chunk at a time — what this used to be | 24 | 2m07 |
| One lens, waves of 4 | 24 | 1m18 |
| Four lenses, triage, waves of 4 — the default | 55 | 2m00 |

Two things to read out of that. Waves alone are worth about a third of the wall
clock, because a batching endpoint answers eight requests in not much longer
than one. And the default spends what that bought on 2.3× as many calls rather
than on finishing sooner — which is how it turned up an unbounded `memcpy` the
single generalist prompt walked past in every run. Triage is what keeps the bill
down: it sent an average of 1.6 specialists per chunk, not five.

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
uv sync                                            # once
cp .env.example .env                               # then edit it
docker compose --profile vllm up -d --wait vllm
docker compose up -d --wait postgres
agent corpus ingest                                # once, and after editing corpus/
```

`.env` is where a machine says which model it serves, which GPUs it has and
where the weights go. Compose reads it on its own:

```
VLLM_MODEL=Qwen/Qwen3.8-27B-FP8
VLLM_TOOL_PARSER=qwen3_coder
VLLM_REASONING_PARSER=qwen3
VLLM_GPUS=0
VLLM_TP=1
HF_HOME=/home/you/.cache/huggingface
```

The default is Qwen3.8-27B at FP8: about 31 GiB of weights, so one 48 GiB card
with `VLLM_TP=1`. FP8 wants sm89 or newer — on an Ampere card vLLM dequantises
to bf16 and the model no longer fits, so pick a GPU accordingly.

`--wait` blocks until the server answers `/v1/models`, which on a cold cache
means the download finished. Nothing has to be told the model id afterwards:
`AGENT_MODEL` unset means ask the endpoint, and the served id is the only right
answer.

| Variable | Default | Meaning |
| --- | --- | --- |
| `VLLM_MODEL` | `Qwen/Qwen3.8-27B-FP8` | Hugging Face id |
| `VLLM_GPUS` | `0` | Device ids, e.g. `0,1` |
| `VLLM_TP` | `1` | Tensor-parallel size; `2` with two GPUs |
| `HF_HOME` | `~/.cache/huggingface` | **Where weights are downloaded to** |
| `VLLM_TOOL_PARSER` | `qwen3_coder` | Tool-call parser; must match the model family |
| `VLLM_REASONING_PARSER` | `qwen3` | Only for models that think in-band; blank passes no flag |
| `VLLM_MAX_LEN` | `16384` | Must clear `AGENT_CONTEXT_CHARS` in tokens |
| `VLLM_MAX_SEQS` | `32` | Concurrent sequences; also caps CUDA-graph capture |
| `VLLM_PORT` | `8000` | Host port, vLLM's own default; the API is on 8001 |

vLLM runs in Docker because the host install cannot work: vllm 0.17 against
torch 2.4, which predates `torch.library.infer_schema`, and this workspace is on
Python 3.14, which vLLM does not publish wheels for. `--served-model-name` pins
the served id to `agent`, so `AGENT_MODEL` does not change when the weights do.

```bash
docker compose --profile vllm logs -f --tail 200 vllm
docker compose stop vllm                     # keep the container
docker compose --profile vllm rm -sf vllm    # remove it; the weights stay in HF_HOME
```

### Models this has been run against

The parser is the part that is easy to get wrong: vLLM refuses tool calling
without one for the family, and the wrong one breaks it silently — verification
falls back to context-only and says so. `vllm serve --help=all` lists all 33.
Every id here was checked against the Hugging Face API; it is a starting point,
not a whitelist.

| `VLLM_MODEL` | what it is | ~GiB | `VLLM_TOOL_PARSER` | `VLLM_REASONING_PARSER` | GPUs |
| --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3.8-27B-FP8` | thinking; needs an sm89+ card | 31 | `qwen3_coder` | `qwen3` | 1 |
| `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ` | 4-bit code specialist | 19 | `hermes` | | 1 |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | FP16 | 28 | `hermes` | | 1 |
| `mistralai/Devstral-Small-2507` | 24B, built for code agents | 48 | `mistral` | | 2 |
| `openai/gpt-oss-20b` | MXFP4 | 13 | `openai` | *(none: vLLM parses harmony itself)* | 1 |
| `openai/gpt-oss-120b` | MXFP4 | 61 | `openai` | *(none)* | 2 |
| `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct` | 16B MoE | 32 | `deepseek_v3` | | 1 |
| `meta-llama/Llama-3.1-8B-Instruct` | gated: needs `HF_TOKEN` | 16 | `llama3_json` | | 1 |
| `zai-org/GLM-4.5-Air` | 106B MoE | 60 | `glm45` | | 2 |
| `ibm-granite/granite-3.3-8b-instruct` | | 16 | `granite` | | 1 |
| `Qwen/Qwen2.5-0.5B-Instruct` | plumbing test only, finds nothing | 1 | `hermes` | | 1 |

A model wanting two GPUs needs `VLLM_TP=2` with it, or it fails to allocate.

### From the terminal

```bash
export AGENT_BASE_URL=http://localhost:8000/v1
export AGENT_MODEL=agent          # optional; unset asks the endpoint

agent index   path/to/src         # deterministic, no model calls
agent inspect path/to/src -v      # the real thing
agent runs                        # previous runs
agent endpoints                   # what is reachable, and what it serves
```

### Choosing a model

Any model vLLM can serve works -- the table above lists the verified ids, and
`VLLM_MODEL` takes any Hugging Face id. Two things actually constrain the
choice.

**It needs a tool-call parser for its family.** vLLM refuses tool calling
without one and the wrong one breaks it silently, which costs verification its
tools. `vllm serve --help=all` lists all 33: `hermes`, `qwen3_coder`,
`mistral`, `llama3_json`, `llama4_json`, `openai`, `deepseek_v3`, `glm45`,
`glm47`, `granite`, `jamba`, `phi4_mini_json`, `pythonic`, `kimi_k2`,
`minimax`, `internlm`, `seed_oss`, `xlam` and more. It goes in `.env` beside
the model, because it cannot be guessed from the name.

**It has to be big enough to finish the schema.** Guided decoding guarantees
the output *matches* the schema, not that the model ever finishes it. A model
too small for `ChunkAnalysis` emits a valid-so-far
prefix until it runs out of room -- measured on a 0.5B, which spent 8048 tokens
without closing the object. `AGENT_MAX_TOKENS` (default 4096) bounds that into a
fast, legible failure rather than a slow one, and the log says which model is at
fault.

Treat anything below about 7B as non-viable for this schema. A 4-bit 32B is the
sweet spot on a 48 GB card.

### GPU layout

Both GPUs can be used together: `VLLM_GPUS=0,1 VLLM_TP=2`. Whether it is worth it depends on
how the cards are wired, so measure rather than assume:

```bash
nvidia-smi topo -m                      # NV# means NVLink; NODE means PCIe only
python -c "import torch; print(torch.cuda.can_device_access_peer(0,1))"
```

On this host that reports `NODE` and `False`, so every tensor-parallel
all-reduce is staged through host memory. Without NVLink, add
`--disable-custom-all-reduce`: vLLM's custom all-reduce needs peer access.

Two more consequences when the cards are different generations, as they are
here (sm_89 Ada and sm_86 Ampere):

- **FP8 is unavailable.** It needs sm_89; the A6000 is sm_86. BF16/FP16 and
  INT4 AWQ/GPTQ run on both.
- **The slower card sets the pace.** Tensor parallelism splits work evenly, so
  the result is roughly twice an A6000, not Ada plus Ada.

So tensor parallelism here buys *capacity*, not speed: it is what makes a 32B at
FP16 possible at all. If a 4-bit 32B is good enough, one card is the better
trade — no interconnect cost, and it can be the faster one.

This used to be less of a constraint than it is now. The loop issued one request
at a time — callees before callers, so notes propagate — which kept batch size at
1 and made the missing NVLink barely matter. It no longer does: a wave of chunks
times five specialists puts up to `AGENT_MAX_CONCURRENCY` requests in flight at
once, which is what continuous batching is for and what makes the endpoint's
throughput rather than its latency the number that matters. Two independent
single-GPU servers behind one address now buy something real.

### Testing it

The package ships a small labelled tree at `tests/fixtures/sample/` — five
files, thirteen chunks, a cross-file call chain, and every function marked
VULNERABLE or SAFE in its own header comment. It is the CLI's default target,
so a first run has something to find.

```bash
pytest -q                                        # whole suite, no model needed
agent index packages/agent/tests/fixtures/sample # deterministic; 5 files, 13 chunks
agent                                            # prompts, defaults to that tree
```

`pytest` covers the index, the schema, anchor location, the tool surface, a
real MCP subprocess round trip, the inspection loop against a scripted model,
and the HTTP API. Nothing in it calls a real model, so it is fast and
deterministic; `agent index` proves chunking and ordering on real source.

It is built as an eval set rather than a demo: each vulnerability has a guarded
twin with the same shape.

| Function | Expected |
| --- | --- |
| `fetch_firmware`, `handle_download` | flagged — CWE-78, url reaches `system` unvalidated |
| `store_payload` | flagged — CWE-787, unbounded `memcpy` into a 64-byte buffer |
| `fetch_firmware_guarded`, `handle_download_guarded` | **silent** — no shell, scheme and length checked |
| `store_payload_guarded` | **silent** — bounds checked before the copy |

Score both directions. Flagging the vulnerable half is easy; staying quiet on
the guarded half is what separates a useful analyser from one that flags every
`system()` it sees. Report the two counts separately — a single accuracy number
hides which one you are failing.

### LangSmith

Tracing is LangChain's; the agent adds the part that makes a trace usable.

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=ls-...
export LANGSMITH_PROJECT=ssat-agent      # optional; this is the default
```

`agent endpoints` reports whether it is on, which project, and — when it is on
but no key is set — that traces are going nowhere. That failure otherwise looks
exactly like success.

**Set these in the shell before the process starts.** `langsmith` wraps its
environment reads in `functools.lru_cache`, so a variable assigned from Python
after langsmith has been imported is read once, cached, and ignored. `agent
endpoints` detects that specific case and says so.

A run makes hundreds of calls, so every one is named for what it did and to
what, and carries the run id, chunk id, file and symbol as metadata:

```
analyse:fetch_firmware              step:analyse  run:9ecda9121fbb
gather:CWE-78 download.c:28         step:gather
verify:CWE-78 download.c:28         step:verify
```

Filter by `step:verify` to see every refutation, or by `run:<id>` to isolate one
report. Untagged, the same trace is an undifferentiated column of `ChatOpenAI`.

### Reading the output

```
run 9ecda9121fbb: indexed 5 files, 13 chunks
 ! download.c:28:5: high [CWE-78] Command Injection
     sprintf(cmd, "wget %s -O /tmp/fw.bin", url);
     "url" is interpolated into a shell command without sanitisation...
     fix: Build the command without a shell, or escape the input.
2 finding(s) from 13 chunk(s). 5 candidate(s), 1 refuted, 2 dropped as unlocatable.
```

The counts are deliberately not merged into one number. `dropped as
unlocatable` means the model described a finding whose quoted source could not
be found in the file, so it was discarded rather than pointed at a guessed
line -- a small model will often produce prose there instead of code. A high
count means the prompt is drifting; `-v` prints every rejected anchor.

### Whether the code runs

A reviewer looked at a finding and said: that is real as a pattern, and it is
dead code. Both halves were true, and the report had no way to say the second
one -- a finding in a never-called `static` helper and one in a request handler
arrived looking identical, so the distinction got re-derived by hand once per
finding.

`index/reach.py` answers it from the call graph `links.py` already resolves. No
model call, no new pass over the tree.

| state | meaning |
| --- | --- |
| `live` | reachable from an entry point |
| `unreferenced` | nothing here calls it, but something outside the tree could |
| `unreachable` | nothing calls it, and nothing outside its own file can |
| `excluded` | test, example or generated code |
| `unknown` | the index could not decide |

Three properties are load-bearing.

**It never suppresses anything.** Reach is a label, not a filter. The web folds
`unreachable` and `excluded` into a collapsed group with a count on it; every
finding stays in the list, in the counts, and one click away, and no severity
changes. Dead code gets revived, and a finding deleted for being unreachable is
gone from a report nobody will re-read.

**No model is shown it.** Not triage, not the specialists, not `verify`.
`verify` defaults to refuting when uncertain, so telling it "this is dead code"
would *delete* real findings rather than label them. Reach is a fact about the
tree, so it sits with the id and the span on the server's side of the line
`schema.py` draws, and two runs over one tree stay comparable.

**Saying `unreachable` is the hard part.** Zero callers does not mean dead here:
`links.py` deliberately leaves function pointers and macro-generated calls
unresolved, `MAX_AMBIGUITY` drops over-loaded names, and an uploaded tree is
usually one directory rather than a program. So a unit earns `unreachable` only
if nothing in the tree calls it *and* the language says nothing outside its own
file could -- and not even then if its name appears anywhere as a value, which
is what a callback table looks like. That case is `unknown`.

`agent index` prints it, because it is deterministic and therefore checkable
without a model:

```
$ agent index packages/agent/tests/fixtures/reach
reach: live 2  unknown 1  unreachable 1  unreferenced 1
  unknown      store.c:43 store_payload_via_table  (이름이 값으로 쓰인 곳이 있음 ...)
  unreachable  store.c:33 store_payload_dead  (파일 밖에서 부를 수 없는 선언 · ...)
```

`tests/fixtures/reach/` is four units holding the *same* unbounded `memcpy` and
differing only in whether anything reaches them -- including the trap, a static
function registered in a callback table, which must come back `unknown` and not
`unreachable`. Kept separate from `fixtures/sample/`, which scores
exploitability and whose counts are quoted above.

By default a unit nothing in the tree calls but something outside could seeds
the walk without being called live itself, so a library gets a sensible answer
with no configuration. `AGENT_ENTRY_POINTS=handle_*` is for when the framework
is what calls the handlers.

### From the browser

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8001 \
  --reload --timeout-graceful-shutdown 2 \
  --reload-dir api --reload-dir packages/ssat/src/ssat \
  --reload-dir packages/agent/src/agent --reload-dir packages/graphify/src/graphify
cd web && pnpm dev                # Next.js on :3000
```

Open <http://localhost:3000/inspect>, upload a zip or a set of files, and press
검사 실행. Findings stream in as each chunk finishes; click one for the
explanation, evidence and proposed fix. The `AGENT_*` variables have to be set
in the shell that starts the API, and the banner says so if they are not.

### Tools during verification

The agent is a client of its own MCP server. The tool surface is defined once,
served over stdio, and the agent connects to it exactly as Claude Code or the
MCP Inspector would — there is no second, in-process copy that could drift.

`verify` uses it. Before ruling on a claim the model may look things up:
`find_callers` to see whether the input really is attacker controlled,
`read_source` or `find_definition` for what a callee actually does,
`search_semantic` to ask in a sentence whether a check exists anywhere.
Only that subset is offered; verification is about one claim, and the full
surface invites wandering.

There is no `run_in_sandbox`. It compiled or ran something against the run's
tree, and a run has no tree — the files are rows.

Three of them come from [`graphify`](../graphify/README.md), which turns the
index into a knowledge graph at index time: `graph_path` answers whether the
claimed source really reaches the claimed sink and through what, and does it in
one call rather than a chain of `find_callers` guesses; `graph_neighbours`
answers what a unit touches in every relation at once; `graph_subsystem` answers
what else belongs with it, clustered by what actually depends on what rather
than by directory. No model and no network are involved in building any of it.

The specialists get no tools, deliberately. Their context is assembled from the
index, so two runs over the same tree are comparable. Letting them browse would
make them not be.

Tool calling needs server support: vLLM rejects it unless started with
`--tool-call-parser` for the model family.

The compose service sets `--tool-call-parser` already; override it with
`VLLM_TOOL_PARSER` for a different model family.

`--reasoning-parser` is the separate case. A model that thinks in-band — Qwen3.8
does, and has thinking on by default — returns that thinking as `content` unless
vLLM is told how to split it out, which leaves guided decoding reading prose
where the JSON should be. `VLLM_REASONING_PARSER` supplies it; blank means the
flag is not passed at all, which is right for gpt-oss, whose format vLLM handles
on its own.

Without it the run verifies from context alone, says so once, and continues.
That is a supported mode, not a broken one — most claims are decidable from the
context pack. Set `AGENT_TOOLS=0` to force it off.

The server can still be driven on its own, which is useful when a tool itself is
misbehaving:

```bash
AGENT_RUN_ID=<run> agent-mcp                # stdio
```

## SEC-bench

The public benchmark, run offline. Each instance is a real CVE: a ~3GB image, an
inspection, a patch, and their evaluator's verdict on it — roughly half an hour
each, over two hundred of them.

```bash
agent bench status      # every knob, and how much has been done
agent bench fetch       # the dataset; 3.7MB
agent bench run         # inspect and patch the selection
agent bench score       # their evaluator over the accumulated patches
agent bench sweep       # all of the above, unattended
```

Split into steps because each has a different cost and a different way of going
wrong: `fetch` is network, `prepare` is gigabytes of it, `run` is the model, and
`score` is a compiler. `sweep` is the one you start in tmux and walk away from —
it checks every cheap precondition first (a model answering, its own Docker
daemon up, the disk actually writable, room on both filesystems), because the
failure worth preventing is discovering at hour six that the model was down and
ten instances failed identically.

It logs to `$SECB_ROOT/sweep.log` as well as to the terminal, and it is
resumable: an instance that already has a result is skipped, so a re-run after a
crash, a reboot or a Ctrl-C continues where it stopped. There is no `--detach` —
tmux, screen or nohup does that better. 벤치마크 in the web UI starts and follows
the same command.

Every setting is an `SECB_*` variable read from the environment or `.env`, and
they are all in one place with their reasons: `src/agent/bench/config.py`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_BASE_URL` | `http://localhost:8000/v1` | OpenAI-compatible endpoint |
| `AGENT_MODEL` | *(the endpoint's, when it serves one)* | Model id the endpoint serves |
| `AGENT_DATABASE_URL` | `postgresql+psycopg://ssat:ssat@localhost:5432/ssat` | Where runs live |
| `AGENT_CONTEXT_CHARS` | `24000` | Context-pack budget per chunk |
| `AGENT_MAX_TOKENS` | `4096` | Ceiling on one response; bounds a model that cannot finish the schema |
| `AGENT_MAX_VERIFY_PER_CHUNK` | `8` | Cap on refute calls per chunk |
| `AGENT_TOOLS` | `1` | Let verification call MCP tools; `0` disables |
| `AGENT_MAX_TOOL_CALLS` | `4` | Tool calls allowed per finding |
| `AGENT_WAVE_WIDTH` | `4` | Chunks inspected at once, at one call depth |
| `AGENT_MAX_CONCURRENCY` | `16` | Ceiling on requests actually in flight |
| `AGENT_LENSES` | *(all five)* | Comma-separated: `memory,injection,access,crypto,logic` |
| `AGENT_TRIAGE` | `1` | Screen each chunk before the specialists; `0` runs them all |
| `AGENT_ENTRY_POINTS` | *(none)* | Symbol globs that are entry points whatever the call graph says, e.g. `handle_*` |

## Layout

```
src/agent/
  languages.py     per-grammar node names, one table
  index/
    chunk.py       tree-sitter -> chunks
    links.py       symbol resolution -> edges
    order.py       topological order, call depth, waves
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

## Storage

A run is one row in Postgres and everything that cascades off it — its files,
its chunks and links, its spans, its checkpoints, its report. It used to be a
directory holding an extracted source tree, three SQLite databases and three
JSON files, held together by a path convention; there was no way to query
across runs and no transaction spanning a run's own state.

`docker compose up postgres` is the whole setup. The schema comes from
`create_all` rather than Alembic, which is a considered trade for a
laptop-scale tool and the first thing to revisit: a column change needs a
manual drop and recreate.

One table is deliberately not per-run. `results` is keyed by chunk id alone, so
a second run over unchanged code reuses what the first concluded — that is what
"지난 검사에서 가져옴" means in the UI.

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
- **Stopping costs coverage, never results.** 중단 sets a flag the graph reads
  between frames *and* every node reads before it calls a model, so a cancelled
  run issues no new requests and ends once the ones in flight return — one
  request, not the whole wave of `wave_width × lenses`. It cannot abort a
  request already on the wire: a blocking `invoke` is not cancellable from
  another thread, so the honest promise is seconds, not instant, and the UI says
  중단하는 중 rather than claiming past tense. Everything already reduced is
  saved, and a claim whose verifier was never reached survives as an unverified
  candidate rather than being read as refuted — the run is `cancelled`, never
  `done`, because `done` says the tree was read.
