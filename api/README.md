# F2-A Test API

A thin FastAPI service over `ssat.cpg` (CPG generation via Joern) and
`ssat.f2a` (evidence extraction). It backs the `web-f2a` testing frontend and
deliberately avoids the older template/ast/dfg modules.

## CPG generation is embedded (no Docker)

CPG generation runs Joern **in-process** via an embedded JVM (JPype) — see
`ssat.cpg.embedded`. There is no Docker container, subprocess, or server to
manage; Joern's JARs are loaded into a JVM inside the API process and its
`JoernParse`/`JoernExport` entrypoints are called directly, producing the same
GraphSON `joern-export` does. The JVM starts on the first request and is reused.

Requirements:
- A **JDK** on the host (Java 17+; tested on 21).
- A **Joern install** on the host. Set `JOERN_HOME` to its `joern-cli`
  directory (default `/usr/bin/joern/joern-cli`).

`GET /health` reports `{"mode": "embedded", "joern_home": ...}`.

## Endpoints

| method | path | body | returns |
| --- | --- | --- | --- |
| GET | `/health` | — | `{status, joern_container}` |
| POST | `/cpg` | `{source, language, filename?}` | `{cpg, method_count}` |
| POST | `/f2a` | `{cpg}` | `F2AResult` |
| POST | `/analyze` | `{source, language, filename?}` | `{cpg, method_count, f2a}` |

`language` is one of `c` / `cpp` / `java`. `cpg` is a Joern GraphSON document
(`{"@type": ..., "@value": {vertices, edges}}`).

## Running

Requires a host JDK + Joern install (see above) and the workspace venv
(`uv sync`). No Docker container needed. From the repo root:

```bash
JOERN_HOME=/usr/bin/joern/joern-cli \
  uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir .
```

For development with auto-reload, use `scripts/dev-api.sh` instead — it runs
uvicorn `--reload` watching `packages/ssat/src/ssat` and `api`, so `.py` edits
restart the worker automatically (no manual restart). The embedded Joern JVM
re-attaches on the first request after each reload, so that request is a few
seconds slower. Without `--reload` the server holds imported code in memory and
must be restarted manually to pick up changes.

CORS is open so the Next.js dev server (localhost or tailnet) can call it.

## Notes

- CPG generation is fully in-process (embedded JVM); the first request pays the
  JVM start-up cost, then the JVM is reused and generation is serialised.
- `POST /analyze` is one round trip: generate the CPG, then run F2-A on it.
