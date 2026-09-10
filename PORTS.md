# Ports on this machine

Allocated 2026-09-10. Each of the five projects under `/home/devel03` owns a 100-wide
band in the 4000s. Numbers are packed sequentially from `X00`; the digit carries no
cross-project meaning, so this table is the lookup.

Host-side ports only. The right half of a compose `ports:` mapping is container-internal,
never collides, and was deliberately left alone — Postgres still listens on 5432 and
MySQL on 3306 *inside* their containers.

| Band | Project |
| --- | --- |
| 4000–4099 | `ev-fuzzer` |
| 4100–4199 | `secure-ev-web` |
| 4200–4299 | `bas-platform` |
| 4300–4399 | `agents` |
| 4400–4499 | `static-software-analysis-tool` |

## 4000s — ev-fuzzer

| Port | Service | Set in |
| --- | --- | --- |
| 4000 | frontend (playground UI) | `frontend/package.json` (`dev`, `start`) |
| 4001 | backend API (uvicorn) | `run.sh`, `main.py`, `evfuzzer/api.py` |
| 4002 | charger listener | `run.sh` exports `EVF_LISTEN_PORT` |
| 4003 | OCPP proxy | `evfuzzer/core/config.py` |
| 4004 | SteVe | `docker-compose.steve.yml` (container keeps 8180) |

`run.sh` now pins the listener to 4002. It used to advertise 4002 while the code fell
back to 9000.

## 4100s — secure-ev-web

| Port | Service | Set in |
| --- | --- | --- |
| 4100 | Next.js web | `apps/web/package.json` (`dev`, `start`) |
| 4101 | MySQL | `docker-compose.yml` + `DATABASE_URL` in `.env` |
| 4102 | Prisma Studio | `packages/prisma/package.json` |

Its MySQL container was renamed `attack-db` → `secure-ev-db`; `bas-platform` already owns
that name. Ports **8888** and **7012** are still expected from the external Defend/Manx
platform and are not this project's to allocate.

## 4200s — bas-platform

| Port | Service | Set in |
| --- | --- | --- |
| 4200 | Next.js web | `apps/web/package.json` |
| 4201 | WebSocket fallback (outbound only) | `apps/web/src/lib/WebSocketService/index.ts` |
| 4202 | MySQL | `docker-compose.yml` + `DATABASE_URL` in `.env` |
| 4203 | Prisma Studio | `packages/prisma/package.json` |

Moved from the 5000–5003 block, which collided with the `agents` registry on 5000. The
running container also came off **6003**, a stale binding no file declared any more.

## 4300s — agents

| Port | Service | Set in |
| --- | --- | --- |
| 4300 | Next.js web | `apps/web/package.json` (`WEB_PORT` default) |
| 4301 | FastAPI api | `package.json` (`API_PORT` default) |
| 4302 | Postgres | `.env` `POSTGRES_PORT` |
| 4303 | Redis | `.env` `REDIS_PORT` |

Two deliberate exceptions:

- **The registry stays on 5000.** Twelve literal `localhost:5000` references across the
  k8s manifests and `package.json`, loopback-only, and nothing contends it now that
  `bas-platform` has vacated 5000.
- **NodePorts 30862 (`vllm`) and 30863 (`infer`) stay.** Kubernetes requires
  30000–32767; they cannot live in a 4000s band.

Note `.env` cannot set the web/api ports — pnpm does not load it, so those two are
defaults in `package.json`. Postgres and Redis *do* come from `.env`, because
`apps/api/app/config.py` reads it by absolute path and builds `DATABASE_URL` from them.

## 4400s — static-software-analysis-tool

| Port | Service | Set in |
| --- | --- | --- |
| 4400 | Next.js web | `web/package.json` (`dev`, `start`) |
| 4401 | FastAPI API | `pyproject.toml` (`dev-api`, `prod-api`) |
| 4402 | Postgres | `docker-compose.yml` `POSTGRES_PORT` default |
| 4403 | vLLM | `docker-compose.yml` `VLLM_PORT` default |

Each of the last two is **two literals**, because the published port and the client URL
that dials it are independent:

| Published port | Client default |
| --- | --- |
| `POSTGRES_PORT` → 4402 | `DEFAULT_DATABASE_URL` in `packages/agent/src/agent/config.py`, and `TEST_DATABASE_URL` in `packages/agent/tests/conftest.py` |
| `VLLM_PORT` → 4403 | `DEFAULT_BASE_URL` in `config.py`, and the probe list in `endpoint.py` |

**Setting `POSTGRES_PORT` alone does not move the client.** It is not derived — the two
were edited in lockstep. Change one and you must change the other, or the API will dial a
port nothing is on. `AGENT_DATABASE_URL` and `AGENT_BASE_URL` override both properly.

`AGENT_TEST_DATABASE_URL` is worth knowing about: `conftest.py` dials it if set, and
otherwise 4402. It appears nowhere else in the repo. If another account ever runs this
suite against a different Postgres port, set it — or `pytest` will `drop_all()` and
`TRUNCATE` whatever is on 4402.

## Not in a band, and not available

| Port(s) | Owner |
| --- | --- |
| 22, 53, 631 | the machine |
| 5000 | `agents` docker registry (loopback) |
| 6443, 6444, 10248–10259, 10250 | k3s — this box is a node |
| 80, 443 | k3s Traefik (LB on 192.168.5.88) |
| 30862, 30863, 32698, 30471 | k3s NodePorts |
| **30000–32767** | the whole k3s NodePort range |
| 17888 | `ssat-service` |
| 8888, 7012 | the external Defend / Manx platform |

**4200 is also the Angular CLI's default.** `bas-platform` is Next.js so nothing clashes,
but an Angular project arriving later needs its own band, not 4200.

## Checking it

```bash
ss -ltnp | grep -E ':4[0-4][0-9][0-9]\b'
docker ps --format '{{.Label "com.docker.compose.project"}} {{.Names}} {{.Ports}}'
kubectl get svc -A -o wide | grep -i nodeport
```

Before handing out a new number, confirm it is actually free — the old `attack-db` on
6003 showed that the runtime and the repo can disagree:

```bash
ss -ltn | grep -E ':(4005|4103|4204|4304|4404)\b'   # expect no output
```
