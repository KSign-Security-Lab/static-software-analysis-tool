# SSAT API

One FastAPI app over two independent lines of analysis, plus the benchmark
surface. `api` imports `agent` and `ssat`; neither imports `api`, and `agent`
imports neither `ssat` nor `gnn`.

| router | prefix | what it is |
| --- | --- | --- |
| `main.py` | — | the structural line: Joern CPG, the SSAT pipeline, F2-A |
| `agent/` | `/agent` | the LLM inspection: runs, findings, patches |
| `bench.py` | `/bench` | read-only public-benchmark results, and the sweep |

## The structural line

CPG generation runs Joern either **in-process** via an embedded JVM (JPype, the
default) or through the Joern container — `ssat.cpg.backends`. The embedded JVM
starts on the first request and is reused, so that request is seconds slower.

Requires a host **JDK** (17+, tested on 21) and a **Joern install**; set
`JOERN_HOME` to its `joern-cli` directory (default `/usr/bin/joern/joern-cli`).

| method | path | body | returns |
| --- | --- | --- | --- |
| GET | `/health` | — | `{status, backends: {jpype, docker}}` |
| POST | `/cpg-jpype`, `/cpg-docker` | `{source, language, filename?}` | `{cpg, method_count, backend}` |
| POST | `/template` | `{source\|cpg, …}` | template nodes |
| POST | `/ast`, `/dfg` | `{source\|cpg, …}` | per-function trees / def-use flow |
| POST | `/analyze-functions` | `{source\|cpg, …}` | AST + DFG per function |
| POST | `/f2a` | `{cpg}` | `F2AResult` |
| POST | `/analyze` | `{source, language, filename?}` | `{cpg, method_count, f2a}` |

`language` is one of `c` / `cpp` / `java`. `cpg` is a Joern GraphSON document
(`{"@type": …, "@value": {vertices, edges}}`). Joern failures are 502; pipeline
failures are 400.

Note that the frontend also derives AST/CFG/DFG/CG *views* from a returned CPG
in TypeScript, by edge label. Those are a different thing from `/ast` and
`/dfg`, which return the SSAT pipeline's own artifacts. Never read one as the
other.

## The LLM line — `/agent`

A run is a tree of source, indexed into units, inspected unit by unit. The tree
is rows in Postgres, never a directory: `agent.db`.

**Intake.** `POST /runs` takes a multipart upload — one `.zip` or a set of files
with the path each had. `POST /runs/git` takes `{url, ref?}` and clones it
shallowly. Both index synchronously and record an `origin` on the run, which is
what later decides whether a fix can be pushed anywhere.

The git route makes the server fetch a URL somebody typed, so it validates
first: `https`/`http` only, no credentials in the URL, and no host that resolves
into a loopback or private range unless `AGENT_GIT_ALLOW_PRIVATE=1`. See
`agent.vcs.check_url` — that function is the security boundary of this endpoint.

**Inspection.** `POST /runs/{id}/inspect` returns immediately; the work runs on a
thread and progress streams over SSE at `GET /runs/{id}/events`, because a
chunk-by-chunk run takes minutes. `POST /runs/{id}/resume` carries
`{action: "resume" | "abort"}`. `GET /runs/{id}/findings` is the report.

**Fixes.** Nothing is ever written back to the analysed tree — that is what makes
a finding's anchor still mean something afterwards and a patch reproducible.

| method | path | body | returns |
| --- | --- | --- | --- |
| POST | `/runs/{id}/propose` | `{finding_id}` | code for a finding that arrived with advice and none |
| POST | `/runs/{id}/patch` | `{finding_ids}` | `{patch, applied, skipped, files}` — a preview |
| POST | `/runs/{id}/archive` | `{finding_ids}` | the whole tree, patched, as a zip |
| POST | `/runs/{id}/push` | `{finding_ids, branch, token, open_pull_request}` | a pushed branch, and a PR on GitHub |

`/patch` reports what it could *not* apply and why — `no_replacement`,
`overlap`, `stale`, `unreadable` — because three of the four are something the
reader can act on. Several fixes in one file are spliced bottom-up so no fix
moves another out from under itself; `agent.remediate.patch_set`.

`/push` takes the caller's token for that one request. It is never stored and
never logged (`agent.vcs.redact` covers every path git's stderr can take), and
it is used only against the URL recorded on the run. This service has no login,
so a server-side token would mean every user of the instance pushing as one
identity.

**Reading a run.** `GET /runs/{id}/{files,file}` for the tree,
`/runs/{id}/{spans,thread,graph}` for what the inspection actually did — which
is what a finding's 판단 과정 is drawn from. All read-only: editing a run's state
mid-flight, replaying one recorded call and adopting a tuned prompt over HTTP
belonged to the studio, and tuning happens through `agent.tuner` now, which
replays a recorded run before it proposes anything.

`GET /runs` is filtered by the `x-ssat-owner` header. That header is **not
authentication** — nothing is challenged and a run is readable by id whoever
asks. It exists because the server is shared and a list of every scan on the box
is mostly other people's.

## Running

```bash
JOERN_HOME=/usr/bin/joern/joern-cli \
  uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir .
```

For development use `scripts/dev-api.sh`, which runs uvicorn `--reload` watching
`packages/{ssat,agent,graphify}/src` and `api`. Postgres is required and is not
behind a compose profile: the API does not start without it.

CORS is open so the Next.js dev server (localhost or tailnet) can call it.

## Notes

- Anything still recorded as `inspecting` at startup belongs to a process that is
  gone, so `lifespan` closes those books once — the difference between a dead run
  reading as failed and it reading as 실행 중 for ever.
- The SSE stream is in-process and cannot be replayed. A tab that arrives
  mid-run has missed everything before it; REST stays the source of truth.
