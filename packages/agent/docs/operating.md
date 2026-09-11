# Operating a run

Testing, tracing and benchmarking [`packages/agent`](../README.md).

## Testing

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

## Tools during verification — the MCP surface

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

Three of them come from [`graphify`](../../graphify/README.md), which turns the
index into a knowledge graph at index time: `graph_path` answers whether the
claimed source really reaches the claimed sink and through what, and does it in
one call rather than a chain of `find_callers` guesses; `graph_neighbours`
answers what a unit touches in every relation at once; `graph_subsystem` answers
what else belongs with it, clustered by what actually depends on what rather
than by directory. No model and no network are involved in building any of it.

The specialists get a narrow subset — `find_definition`, `find_callers`,
`find_callees`, `graph_neighbours` — and at most `AGENT_MAX_LENS_TOOL_CALLS` (2)
of them, so a lens can resolve a callee it does not recognise without wandering.
The retrieval and read tools are deliberately not among them: their context is
assembled from the index, and two runs over one tree should stay comparable.
`AGENT_LENS_TOOLS=0` removes the preamble entirely — worth measuring, since it is
23% of a run's model time and has never been A/B'd.

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

## LangSmith tracing

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
