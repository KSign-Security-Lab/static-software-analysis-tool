# Why the agent is built this way

The decisions behind [`packages/agent`](../README.md), and the evidence for them.

## The five decisions

**Chunks are syntactic, not fixed windows.** A fixed window cuts functions in
half and destroys the only unit worth reasoning about.

**Callees are analysed before their callers.** When a callee is analysed the
model writes a *note* — "returns a buffer built from `req->location` with no
validation" — and that note is injected into every caller's context. Taint
crosses chunk boundaries without the whole tree ever entering one prompt.

**Five narrow analysts, not one broad one.** A single prompt asked to hold
memory safety, injection, access control, cryptographic use and resource
lifetime in mind at once skims all five. Each specialist gets one family of
defect and is told to leave the others alone. A cheap screening call in front of
them decides which of the five a unit has earned, biased to say yes: a false
positive there costs one analysis, a false negative loses a vulnerability.
Measured on the sample tree, triage sent an average of **1.6 specialists per
chunk, not five** — and the five-lens default turned up an unbounded `memcpy`
that the single generalist prompt walked past in every run.

**A chunk is one task, and it goes as soon as its callees are done.** A round
dispatches every queued chunk whose callees have already been analysed — read off
the computed order, so a call cycle cannot deadlock it. Every context pack in a
round is built before any specialist in that round runs, so two chunks going
together can never see each other's notes: **the report does not depend on how
wide a round is**, and a test pins that.

**The model quotes source; the server locates it.** Models get line numbers
wrong, so a finding carries `anchor_text` — the exact offending text — and
`agent.locate` derives the real line and column by finding it. Matching walks a
ladder from exact to whitespace-flexible; if no rung matches, **the finding is
dropped**. A marker on the wrong line is worse than no marker.

### Anchors come back mangled

| Model returned | Source actually says | Rung |
| --- | --- | --- |
| `"snprintf(cmd, \"wget %s\", loc);"` | `snprintf(cmd, "wget %s", loc);` | `dequoted` |
| `"wget %s", url;` | `sprintf(cmd, "wget %s", url);` | `punctuation-trimmed` |

The first is a correct finding a naive substring test would have thrown away.
The second is the model completing a fragment into a statement; trimming the
punctuation it added leaves something that is still an *exact* substring, so it
is recovered without loosening the match.

## Reading the output

The counts are deliberately not merged into one number. `dropped as
unlocatable` means the model described a finding whose quoted source could not
be found in the file, so it was discarded rather than pointed at a guessed
line -- a small model will often produce prose there instead of code. A high
count means the prompt is drifting; `-v` prints every rejected anchor.

## Whether the code runs — reachability labelling

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

## Storage — one row per run

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

## Things that will bite you

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
  between frames, every node reads before it calls a model, and the caller reads
  again after it takes an in-flight slot — so a cancelled run issues no new
  requests even when a round of `wave_width × lenses` tasks is queued behind the
  semaphore. Requests already on the wire end too: closing the endpoint transport
  is the client disconnect vLLM frees a sequence on, and the session does it on
  cancel and on close. Without that a killed run left the server decoding into
  nothing. The UI still says 중단하는 중 rather than claiming past tense, because
  the wind-down is seconds. Everything already reduced is
  saved, and a claim whose verifier was never reached survives as an unverified
  candidate rather than being read as refuted — the run is `cancelled`, never
  `done`, because `done` says the tree was read.
