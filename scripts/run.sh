#!/usr/bin/env bash
#
# Task index for this repo -- the equivalent of package.json "scripts", for the
# parts that are not npm.
#
# Plain bash on purpose. A Makefile would mean installing make to run a CLI, and
# uv has no task runner. This needs nothing that is not already here.
#
#   scripts/run.sh              list the tasks
#   scripts/run.sh <task> ...   run one; extra arguments are passed through
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
VENV="$PWD/.venv"

# name | description | command
# Kept as one table so the listing cannot drift from what actually runs.
TASKS=(
  "setup|Install the Python workspace and the web dependencies|_setup"
  "check|Everything CI runs: lint, format, types, tests, web|_check"
  "test|Python tests|$VENV/bin/python -m pytest -q"
  "lint|ruff check + format check|_lint"
  "fmt|Format Python and web sources in place|_fmt"
  "types|mypy --strict|$VENV/bin/mypy"
  "schema|Regenerate web/lib/agent-schema.ts from the pydantic models|_schema"
  ""
  "vllm|Start a vLLM server (interactive; also stop/status/logs)|scripts/vllm.sh"
  "agent|Run an inspection (interactive)|$VENV/bin/agent"
  "index|Index a tree without calling a model|$VENV/bin/agent index"
  "endpoints|Which model servers are reachable, and LangSmith status|$VENV/bin/agent endpoints"
  "mcp|Serve the tool surface over stdio (needs AGENT_RUN_ROOT)|$VENV/bin/agent-mcp"
  ""
  "api|FastAPI on :8000 with auto-reload|scripts/dev-api.sh"
  "web|Next.js dev server on :3000|_web"
  "build|Production build of the web app|_web_build"
  ""
  "demo|End to end on the sample tree: vLLM, then inspect|_demo"
)

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }

_setup() { uv sync "$@" && (cd web && npm install); }
_lint() { "$VENV/bin/ruff" check && "$VENV/bin/ruff" format --check; }
_fmt() { "$VENV/bin/ruff" format . && "$VENV/bin/ruff" check --fix . && (cd web && npx prettier --write . 2>/dev/null || true); }
_schema() { (cd packages/agent/src && PYTHONPATH=. "$VENV/bin/python" -m agent.schema_ts --write); }
_web() { (cd web && npm run dev); }
_web_build() { (cd web && npm run build); }

_check() {
  info "ruff check";        "$VENV/bin/ruff" check
  info "ruff format";       "$VENV/bin/ruff" format --check
  info "mypy";              "$VENV/bin/mypy"
  info "pytest";            "$VENV/bin/python" -m pytest -q
  info "web type-check";    (cd web && npm run --silent type-check)
  info "web lint";          (cd web && npm run --silent lint)
  info "web test";          (cd web && npm run --silent test)
  info "all green"
}

_demo() {
  local target="packages/agent/tests/fixtures/sample"
  info "1/2  starting a model server"
  scripts/vllm.sh status >/dev/null 2>&1 || scripts/vllm.sh
  info "2/2  inspecting $target"
  "$VENV/bin/agent" inspect -v "$target"
}

usage() {
  awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
  echo
  printf '\033[1mtasks\033[0m\n'
  local entry name desc
  for entry in "${TASKS[@]}"; do
    if [[ -z "$entry" ]]; then echo; continue; fi
    IFS='|' read -r name desc _ <<<"$entry"
    printf '  \033[36m%-11s\033[0m %s\n' "$name" "$desc"
  done
  cat <<'EOF'

Web-only tasks live in web/package.json and are runnable there directly.
EOF
}

main() {
  local wanted="${1:-}"
  [[ -z "$wanted" || "$wanted" == "-h" || "$wanted" == "--help" ]] && { usage; return 0; }
  shift

  local entry name command
  for entry in "${TASKS[@]}"; do
    [[ -z "$entry" ]] && continue
    IFS='|' read -r name _ command <<<"$entry"
    if [[ "$name" == "$wanted" ]]; then
      if [[ "$command" == _* ]]; then
        "$command" "$@"
      else
        # shellcheck disable=SC2086 -- the table stores argv, not a quoted string
        $command "$@"
      fi
      return $?
    fi
  done

  die "unknown task: $wanted (run scripts/run.sh for the list)"
}

main "$@"
