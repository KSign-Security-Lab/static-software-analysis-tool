# SSAT Web

A Next.js 16 / React 19 UI over the whole toolchain. Five surfaces, two shells,
one rail.

| surface | route | what it answers |
| --- | --- | --- |
| **검사** | `/agent` | is there a vulnerability in this code, and what do I do about it |
| **F2-A** | `/f2a` | which function handles this action, and on what evidence |
| **추출** | `/extract` | what does this code's structure look like |
| **스테이지** | `/extract/stages` | what does one pipeline stage actually return |
| **벤치마크** | `/bench` | how far does the agent get on public benchmarks, and where does it break |

Each is declared once in `lib/workbench/perspectives.ts` — label, purpose, and a
step-by-step walkthrough that the rail's 사용법 popover renders. That file is the
closest thing this app has to a design document; read it before changing a
surface.

## Two shells, and why

**검사 has its own** — `app/(inspect)/`. It is a flow: give code, read findings,
take a patch. A rail and one region, and the stage is derived from the run's own
state rather than stored (`lib/inspect/stage.ts`).

It was an IDE for most of its life — a Monaco editor, a file tree, file tabs,
per-file drafts, in-place patching — and the layout was rebuilt, reverted and
rebuilt again before it became clear the IDE framing was the problem rather than
the arrangement of its panes. Everything that used to be a pane beside the
finding is now a section *of* the finding, including the two that explain how it
was reached: 판단 과정 (the calls that produced the claim) and 에이전트 구조 (the
path it took through the graph), both closed until asked for.

**The other four share the workbench** — `app/(workbench)/`, a four-slot
resizable shell with parallel routes (`@side`, `@dock`, `@inspector`) and pane
sizes read from a cookie on the server so the first paint is already correct
(`lib/workbench/layout-cookie.ts`). Comparing a graph against the code that
produced it is exactly what resizable panes are for.

## Architecture

- **Transport** — `lib/api/client.ts` is the only place the browser talks to the
  backend. One base-URL resolution, one error vocabulary. `lib/api/events.ts` is
  the only file allowed to construct an `EventSource` (ESLint enforces it).
- **Server cache** — TanStack Query, `staleTime: Infinity`, no retry on 4xx.
  Keys in `lib/query/keys.ts`; the SSE stream invalidates by prefix.
- **URL state** — nuqs. `?run=`, `?finding=`, `?span=`, `?sort=` for 검사;
  `?sample=`, `?view=`, `?stage=`, `?dataset=`, `?instance=` elsewhere.
- **Findings** — `lib/model/finding.ts` is one shape for both engines. The LLM
  agent and F2-A answer the same question about the same code and used to have
  nothing in common on screen; they still run independently, but a result is
  described the same way.
- **Types** — `lib/agent-schema.ts` and `lib/f2a-schema.ts` are **generated** from
  pydantic (`python -m agent.schema_ts --write`, `python -m ssat.schema_ts --write`)
  and a test fails on drift. Do not hand-edit.
- **Design tokens** — `app/theme.css`, three layers: private OKLCH ramps →
  semantic roles per theme → `@theme inline` exposing both the SSAT vocabulary
  (`bg-surface`, `text-ink-muted`) and the shadcn contract. `/dev/tokens` renders
  every primitive and token; dev-only.

## Running

```bash
docker compose up -d --wait postgres    # the API does not start without it
uv run uvicorn api.main:app --port 4401 --reload --timeout-graceful-shutdown 2 \
  --reload-dir api --reload-dir packages/ssat/src/ssat \
  --reload-dir packages/agent/src/agent --reload-dir packages/graphify/src/graphify
cd web && pnpm install && pnpm dev      # :4400
```

Override the backend with `NEXT_PUBLIC_API_URL` (see `.env.local.example`). Over
Tailscale, set that and `ALLOWED_DEV_ORIGINS` to your tailnet IP:

```bash
NEXT_PUBLIC_API_URL=http://100.x.y.z:4401 ALLOWED_DEV_ORIGINS=100.x.y.z pnpm dev
```

## Scripts

| script | what |
| --- | --- |
| `pnpm dev` | dev server on :4400 |
| `pnpm build` / `pnpm start` | production build / serve |
| `pnpm type-check` | `tsc --noEmit` |
| `pnpm lint` | ESLint, including the dead-class and EventSource rules |
| `pnpm test` | Vitest — two projects, `lib` in node and `ui` in jsdom |
| `pnpm run licenses` / `pnpm run licenses:check` | the dependency licence gate CI runs |

`pnpm build` is part of the gate and not redundant with `type-check`: `tsc`
does not catch a server component importing a client-only module, or a broken
`dynamic()` boundary.

The two licence scripts need `pnpm run`: `pnpm licenses` is pnpm's own command
and shadows the script name. It fails loudly rather than quietly doing nothing,
but `run` is the habit to have.

pnpm, not npm — `packageManager` in `package.json` pins the version and
`pnpm-workspace.yaml` holds the one setting we set: an allowlist of the
dependencies permitted to run install scripts, which is `unrs-resolver` and
nothing else.

### Screenshots

`node scripts/shot.mjs <url> <out.png>` drives Chrome over the DevTools protocol.
`chrome --screenshot` fires on the load event, before React has rendered anything
the queries fetched, and `--virtual-time-budget` hangs forever here because 검사
holds an SSE connection open. Takes `--click`, `--eval` and `--wait`, and prints
the console — a screenshot that looks right while the console is full of errors
is not a passing check.
