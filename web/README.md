# SSAT Web

A Next.js + TypeScript UI over the whole toolchain: turn source into a **Code
Property Graph**, inspect it, and see both the **F2-A** evidence pipeline and
the **SSAT extraction pipeline** run over it.

```
 source ──▶ FastAPI /analyze ───────▶ CPG (GraphSON) ──▶ ssat.f2a ──▶ evidence
 CPG ──▶ browser (TS) ─────────────▶ AST / CFG / DFG / CG views   (by edge label)
 CPG ──▶ FastAPI /analyze-functions ▶ AST / DFG per function       (SSAT pipeline)
```

## Two senses of "AST" and "DFG"

The tab bar groups them, because they are genuinely different objects:

| group | tab | what it is |
| --- | --- | --- |
| **CPG** | AST, CFG, DFG, CG, CPG | Joern's own graph, projected client-side by edge label (`lib/views.ts`) |
| **파이프라인** | AST, DFG | what `ssat.ast` / `ssat.dfg` compute from the Template — statement-level tree and def-use flow (`lib/pipeline.ts`) |

The CPG views answer *"what did Joern see?"*. The pipeline views answer *"what
does SSAT extract for the GNN?"*. Never read one as the other.

## Architecture

- **Backend** — `../api/main.py` (FastAPI). `GET /health`, `POST /cpg-jpype`,
  `POST /cpg-docker`, `POST /template`, `POST /ast`, `POST /dfg`,
  `POST /analyze-functions`, `POST /f2a`, `POST /analyze`. CPG generation runs
  either in-process (JPype, the default) or via the Joern container.
- **Frontend** — this app.
  - `lib/cpg.ts` parses the Joern GraphSON (unwrapping `@value`, indexing edges,
    building the AST-parent map for `methodOf`).
  - `lib/views.ts` projects each view purely by **edge label**
    (`AST`, `CALL`, `REACHING_DEF`, `CFG`) — mirroring `ssat.f2a`'s CPGModel.
  - `lib/layout.ts` lays graphs out with dagre and renders via React Flow.
  - `lib/pipeline.ts` converts the SSAT pipeline's per-function AST/DFG JSON
    into the same `GraphView` shape, so one renderer draws both kinds of graph.
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
   cd web
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
| `npm run test` | Vitest — CPG extraction and pipeline-view conversion |
| `npm run lint` | ESLint |
