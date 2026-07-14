# F2-A Test API

A thin FastAPI service over `ssat.cpg` (CPG generation via Joern) and
`ssat.f2a` (evidence extraction). It backs the `web-f2a` testing frontend and
deliberately avoids the older template/ast/dfg modules.

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

Requires the Joern container (`docker compose up -d`) and the workspace venv
(`uv sync`). From the repo root:

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --app-dir .
```

CORS is open to any `localhost` origin so the Next.js dev server can call it.

## Notes

- CPG generation runs `joern-parse` + `joern-export` inside the container via the
  shared `workspace/` volume, so the service must run from the repo root (where
  that volume is mounted).
- `POST /analyze` is one round trip: generate the CPG, then run F2-A on it.
