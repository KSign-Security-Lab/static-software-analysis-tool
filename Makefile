# Developer tasks for SSAT.
#
# These used to be console scripts declared in packages/ssat/pyproject.toml --
# `lint`, `format`, `test`, `docker-up` and friends -- which meant `uv sync`
# installed commands with those bare names into the venv's bin directory,
# shadowing whatever else was on PATH. They are just shell commands; they belong
# here.
#
#   make help     list targets
#   make check    everything CI runs

JOERN_CONTAINER ?= ssat-joern-$(USER)
PYTHON_PATHS    := packages api
WEB             := web

.DEFAULT_GOAL := help

.PHONY: help
help:  ## List available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- python ----

.PHONY: sync
sync:  ## Install/refresh the workspace venv
	uv sync

.PHONY: test
test:  ## Run the Python test suite
	uv run pytest packages/ssat/tests $(ARGS)

.PHONY: golden
golden:  ## Re-record golden snapshots (review the diff -- they guard the refactor)
	uv run python packages/ssat/tests/generate_golden.py

.PHONY: lint
lint:  ## ruff check
	uv run ruff check $(PYTHON_PATHS)

.PHONY: lint-fix
lint-fix:  ## ruff check --fix
	uv run ruff check --fix $(PYTHON_PATHS)

.PHONY: format
format:  ## ruff format
	uv run ruff format $(PYTHON_PATHS)

.PHONY: format-check
format-check:  ## ruff format --check
	uv run ruff format --check $(PYTHON_PATHS)

.PHONY: type-check
type-check:  ## mypy --strict
	uv run mypy packages/ssat/src/ssat api

.PHONY: check
check: lint format-check type-check test web-check  ## Everything CI enforces

# ------------------------------------------------------------------- web ----

.PHONY: web-dev
web-dev:  ## Next.js dev server
	cd $(WEB) && npm run dev

.PHONY: web-build
web-build:  ## Production build
	cd $(WEB) && npm run build

.PHONY: web-test
web-test:  ## vitest
	cd $(WEB) && npm run test

.PHONY: web-check
web-check:  ## Type-check, lint and test the web app
	cd $(WEB) && npm run type-check && npm run lint && npm run test

.PHONY: api
api:  ## FastAPI backend with auto-reload
	scripts/dev-api.sh

# ---------------------------------------------------------------- joern -----

.PHONY: docker-up
docker-up:  ## Start the Joern container
	docker compose up -d

.PHONY: docker-down
docker-down:  ## Stop the Joern container
	docker compose down -v

.PHONY: docker-logs
docker-logs:  ## Follow Joern container logs
	docker logs -f $(JOERN_CONTAINER)

.PHONY: docker-fresh
docker-fresh:  ## Rebuild the Joern image from scratch
	docker compose down -v
	docker compose build --no-cache
	docker compose up -d

.PHONY: backends
backends:  ## Report which CPG backends can run here
	@uv run python -c "from ssat.cpg.backends import EmbeddedBackend, DockerBackend; \
	  [print(f'{b.name:8} {\"available\" if b.is_available() else \"unavailable\"}') \
	   for b in (EmbeddedBackend(), DockerBackend())]"
