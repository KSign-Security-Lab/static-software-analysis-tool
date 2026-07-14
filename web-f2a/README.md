# F2-A Test Web

A Next.js + TypeScript testing UI that turns source code into a **Code Property
Graph** and lets you inspect its four graph views — **AST · CG · DFG · CFG** —
alongside the **F2-A** OCPP-native evidence pipeline.

It is built entirely on `ssat.cpg` (CPG generation via Joern) and `ssat.f2a`
(evidence extraction). It does **not** use the older `ssat` template/ast/dfg
modules.

```
 source ──▶ FastAPI /analyze ──▶ ssat.cpg (Joern) ──▶ CPG (GraphSON)
                                        └──────────▶ ssat.f2a ──▶ evidence
 CPG (GraphSON) ──▶ browser (TS) ──▶ AST / CG / DFG / CFG views (React Flow)
```

## Architecture

- **Backend** — `../api/main.py` (FastAPI). Endpoints: `GET /health`,
  `POST /cpg`, `POST /f2a`, `POST /analyze`. Imports `ssat.cpg` + `ssat.f2a`
  in-process; CPG generation shells into the Joern container.
- **Frontend** — this app.
  - `lib/cpg.ts` parses the Joern GraphSON (unwrapping `@value`, indexing edges,
    building the AST-parent map for `methodOf`).
  - `lib/views.ts` projects each view purely by **edge label**
    (`AST`, `CALL`, `REACHING_DEF`, `CFG`) — mirroring `ssat.f2a`'s CPGModel.
  - `lib/layout.ts` lays graphs out with dagre and renders via React Flow.
  - `components/F2AReport.tsx` renders the evidence packages (flow, observed /
    missing checks, confidence breakdown, limitations).

## Running

1. **Start the backend** (from the repo root — needs the Joern container up:
   `docker compose up -d`):

   ```bash
   uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --app-dir .
   ```

2. **Start the frontend**:

   ```bash
   cd web-f2a
   npm install
   npm run dev        # http://localhost:3000
   ```

   Override the backend URL with `NEXT_PUBLIC_API_URL` (see `.env.local.example`).

3. Load a sample (or paste C/C++/Java), press **Analyze**.

### Reading complex CPGs without the hairball

- **Story** (default tab) leads with the F2-A source→sink path as a legible
  vertical flow — observed checks inline (✓), missing/negative checks (✗/○) near
  the sink, plus a confidence breakdown. It shows only the meaningful subgraph.
- **AST / CFG / DFG / CG / CPG** are drill-downs, each with reducers so they stay
  readable:
  - **function picker** — scope a view to one method (kills node count);
  - **simplify** — fold `<operator>.*` / literals / blocks, reconnecting edges;
  - **edge-layer toggles** — choose which edge labels to overlay;
  - **search + focus** — find nodes, click one to isolate its 2-hop neighbourhood.
- **Report** keeps the full tabular F2-A output.

Over Tailscale, set `ALLOWED_DEV_ORIGINS` and `NEXT_PUBLIC_API_URL` to your
tailnet IP, e.g.:

```bash
NEXT_PUBLIC_API_URL=http://100.x.y.z:8000 ALLOWED_DEV_ORIGINS=100.x.y.z npm run dev
# backend: uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir .
```

## Scripts

| script | what |
| --- | --- |
| `npm run dev` | dev server on :3000 |
| `npm run build` / `npm run start` | production build / serve |
| `npm run type-check` | `tsc --noEmit` |
| `npm run test` | Vitest — verifies the CPG extraction against a real fixture |
| `npm run lint` | ESLint |
