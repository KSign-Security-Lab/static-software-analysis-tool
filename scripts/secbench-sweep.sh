#!/usr/bin/env bash
# A SEC-bench sweep you can start and walk away from.
#
#   scripts/secbench-sweep.sh --detach          # start it and go home
#   scripts/secbench-sweep.sh                   # watch it
#   SECB_LIMIT=10 scripts/secbench-sweep.sh     # a sample first
#
# Checks everything cheap before it spends anything expensive, because the
# failure worth preventing is discovering at hour six that the model was down
# and ten instances failed identically.
#
# Resumable. `agent bench run` skips instances that already have a result, so
# re-running this after a crash, a reboot or a Ctrl-C continues where it stopped
# rather than starting over. That is what makes it safe to leave.
#
# Every knob lives in packages/agent/src/agent/bench/config.py and is read from
# the environment; this script sets none of them and only reports what they are.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
ROOT="$(pwd)"
VENV="${ROOT}/.venv/bin"

# .env is where this machine says where its space is. Compose reads it
# automatically; this script has to be told.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

SECB_ROOT="${SECB_ROOT:-${ROOT}/artifacts/secbench}"
LOG="${SECB_ROOT}/sweep.log"

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# -- detach ------------------------------------------------------------------
#
# Re-exec under setsid so the sweep outlives the terminal. Explicit rather than
# automatic: a script that silently backgrounds itself is one you cannot watch.
if [[ "${1:-}" == "--detach" ]]; then
  mkdir -p "${SECB_ROOT}"
  # The child tees to the log itself, so this discards rather than
  # duplicating every line into it.
  setsid nohup "$0" >/dev/null 2>&1 < /dev/null &
  info "sweep started in the background (pid $!)"
  info "  log:    tail -f ${LOG}"
  info "  stop:   pkill -f secbench-sweep.sh"
  exit 0
fi

mkdir -p "${SECB_ROOT}"
# Always, whether or not there is a terminal. A sweep run from cron, or with its
# output piped, is exactly the one whose log you will want afterwards.
exec > >(tee -a "${LOG}") 2>&1
info "SEC-bench sweep — $(date '+%Y-%m-%d %H:%M:%S')"

# -- preconditions -----------------------------------------------------------
#
# All of them, before any of the expensive steps. Each one has actually cost an
# afternoon somewhere.

step "checking"

fail=0
need() { command -v "$1" >/dev/null 2>&1 || { red "missing: $1"; fail=1; }; }
need docker
[[ -x "${VENV}/agent" ]] || { red "no ${VENV}/agent — run: uv sync"; fail=1; }

# The model. Every instance is an inspection, so without this the sweep produces
# a long row of identical failures.
BASE="${AGENT_BASE_URL:-http://localhost:8001/v1}"
if ! curl -sf --max-time 10 "${BASE}/models" >/dev/null 2>&1; then
  red "no model answering at ${BASE}"
  red "  start one:  docker compose --profile vllm up -d --wait vllm"
  fail=1
else
  SERVED="$(curl -sf --max-time 10 "${BASE}/models" | "${VENV}/python" -c \
    'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])' 2>/dev/null)"
  export AGENT_MODEL="${AGENT_MODEL:-${SERVED}}"
  export AGENT_BASE_URL="${BASE}"
  info "  model            ${AGENT_MODEL} at ${BASE}"
fi

# The sweep's own daemon. Its images must not land on the system disk.
if ! docker compose --profile secbench ps --status running 2>/dev/null | grep -q secbench-docker; then
  info "  starting the sweep's docker daemon"
  docker compose --profile secbench up -d --wait secbench-docker || { red "could not start it"; fail=1; }
fi

# Two disks matter and they are not the same one. Images go to SECB_DOCKER_ROOT;
# the tooling image builds on the *host* daemon, which is usually /.
host_free=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
data_free=$(df -BG --output=avail "${SECB_ROOT}" 2>/dev/null | tail -1 | tr -dc '0-9')
info "  free             / ${host_free}G · ${SECB_ROOT} ${data_free}G"
[[ "${host_free:-0}" -lt 4 ]] && { red "under 4G free on / — the tooling image builds there"; fail=1; }
[[ "${data_free:-0}" -lt 20 ]] && { red "under 20G free on ${SECB_ROOT} — evaluation images go there"; fail=1; }

if [[ "${SECB_PRUNE:-1}" == "0" ]]; then
  red "  SECB_PRUNE=0 — images are kept. The full set is ~200G on a shared volume."
fi

[[ "${fail}" -ne 0 ]] && { echo; red "refusing to start"; exit 1; }

"${VENV}/agent" bench status

# -- the sweep ---------------------------------------------------------------

step "dataset"
"${VENV}/agent" bench fetch || { red "fetch failed"; exit 1; }

step "sweeping"
info "each instance is a ~1-3GB pull, an inspection and a patch — allow ~30 minutes each"
info "safe to interrupt: a re-run skips what already finished"
started=$(date +%s)
"${VENV}/agent" bench run
ran=$?
info "sweep phase finished in $(( ($(date +%s) - started) / 60 )) minutes"

# -- scoring -----------------------------------------------------------------
#
# Theirs, not ours. Built once; the image is pinned so a later sweep scores the
# same way.

step "scoring"
# Unconditional: a cached build is a no-op, and guessing the built image's name
# from the compose project is fragile in a way that failing to build is not.
info "building SEC-bench's tooling image (cached after the first run)"
docker compose --profile secbench build secbench \
  || { red "build failed — the patches are still in ${SECB_ROOT}/preds.json"; exit 1; }
docker compose --profile secbench up -d secbench >/dev/null 2>&1
"${VENV}/agent" bench score || red "scoring failed — the sweep's own results are intact"

# -- done --------------------------------------------------------------------

step "done"
"${VENV}/agent" bench status
info "results     ${SECB_ROOT}/results"
info "patches     ${SECB_ROOT}/preds.json"
info "on screen   http://localhost:3000/bench?dataset=sec-bench"
info ""
info "the daemon is still up; stop it with:"
info "  docker compose --profile secbench down"
exit "${ran}"
