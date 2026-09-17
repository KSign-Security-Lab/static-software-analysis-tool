# Development

Task list, containers, snapshots and the reasoning behind them. The short
version is in the [root README](../README.md#development).

## Development

The task list is `[tool.poe.tasks]` in the root `pyproject.toml`, and
[poethepoet](https://poethepoet.natn.io/) runs it:

```bash
uv run poe               # the list, with what each one does
uv run poe check         # lint, types, Python tests, then the web gate
uv run poe dev           # the API and the web app together
uv run poe dev-api       # just the API on :4401, with reload
uv run poe dev-web       # just the Next.js dev server on :4400
uv run poe stack         # what is running right now
```

`dev` and `prod` run both halves at once in one terminal, with each line
prefixed by the task it came from. One Ctrl-C stops both; poe has no background
mode, so use tmux if you want them detached.

Every task that runs the app names its mode, because the two behave differently
enough to be worth telling apart: `dev-api` reloads on edit and `dev-web` serves
through HMR, while `prod-api` runs one process with no reloader and `prod-web`
builds first and serves the build. Reach for the `prod-` pair when something
only misbehaves in a real build. Neither is a deployment: there is no app image
and no `api` or `web` service in Compose, so both run here on your machine.

`prod-api` runs a single process on purpose. Do not add `--workers`: the SSE
channels in `api/agent/channels.py` are a module-global dict, so with two
workers a `GET /events` can land on the one that never saw the `POST` and the
stream never attaches. Both API tasks pass `--timeout-graceful-shutdown`, which
caps the wait on an idle `/events` stream that otherwise reads as a hang.

The list reaches the web app too — those tasks set `cwd = "web"` and run
`pnpm`, so one file covers both halves of the repo. It is short on purpose:
a task earns its place by composing several commands or by carrying arguments
that are easy to get wrong. Anything that is one short command is not in it, so
the `agent` CLI is run directly — `uv run agent index src/`.

Nothing is hidden behind it. Every task is the real command and running it
yourself works exactly the same:

```bash
ruff check
ruff format --check
mypy
pytest

cd web && pnpm type-check && pnpm lint && pnpm test
```

No path arguments: the targets live in `pyproject.toml`, so there is one
definition of what gets checked rather than one per caller. CI calls the tools
directly rather than going through poe — see `.github/workflows/ci.yml` — so a
mistake in the task list cannot turn a build green.

The containers, by name — `vllm` and `secbench` are profile-gated, and Compose
silently matches nothing if the profile is left off:

```bash
docker compose ps -a                                     # what is up
docker compose up -d --wait postgres                     # start
docker compose --profile vllm up -d --wait vllm
docker compose --profile vllm logs -f --tail 200 vllm    # follow one
docker compose stop vllm                                 # stop, keep it
docker compose --profile vllm rm -sf vllm                # remove the container
```

Removing a container is safe: stored runs live in a named volume, the weights in
`HF_HOME`, and SEC-bench's images in its own daemon's data root. None of the
three goes with the container.

The other things worth knowing about:

```bash
python -m agent.schema_ts --write && python -m ssat.schema_ts --write
agent inspect -v packages/agent/tests/fixtures/sample
agent bench sweep
```

The first regenerates `web/lib/agent-schema.ts` from the pydantic wire models
and a test fails on drift. The second is the end-to-end check that a model
server, the database and the graph all work. The third is the unattended
SEC-bench sweep — see `packages/agent/README.md`.


## Golden snapshots

They belong to `ssat` and are documented with it:
[packages/ssat/README.md](../packages/ssat/README.md#golden-snapshots).
