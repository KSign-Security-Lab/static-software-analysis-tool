"""One instance: pull it, read the crash, inspect it, produce a patch.

The shape of an attempt is deliberately the shape of an ordinary inspection.
Files go into a real run row, `InspectionSession` reads them, findings land in
the report, and the patch comes out of `remediate.splice` -- the same function
behind 이대로 고치기. So `instance.run_id` on the 벤치마크 surface opens a trace,
a pipeline drawing and a tool-call record like any other run, and the sweep
cannot quietly diverge from what a person pressing the button would get.

What the agent is shown is the sanitizer report's stack trace and the CVE text.
Not the files the reference patch touches: that would be telling it where the
bug is and then scoring it on finding the bug.

Nothing here is imported by the graph or the API. A benchmark you can trigger
from a request is one you will iterate against.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from typing import Sequence

from ..config import AgentConfig
from ..graph.build import run_inspection
from ..index import build_index
from ..remediate import Stale, splice, unified_diff
from ..runs import new_run, write_files
from ..schema import Finding, Report
from .config import BenchConfig
from .dataset import Instance

log = logging.getLogger(__name__)


@dataclass
class Attempt:
    """What one instance produced. Written beside the run, read by the surface."""

    instance_id: str
    #: The run this became, so the surface can open it in 검사.
    run_id: str | None = None
    config_hash: str | None = None
    #: Repo-relative paths the sweep actually put in front of the agent.
    shown: list[str] | None = None
    #: `model_patch` for `preds.json`. Empty means we produced nothing.
    patch: str = ""
    #: Which finding the patch came from, if any.
    finding_id: str | None = None
    cwe: str | None = None
    #: Set when the attempt did not get as far as a patch, in the runner's own
    #: words. The evaluator decides the later stages; this decides the earlier
    #: ones, and saying which is which is the point of the taxonomy.
    stage: str = ""
    note: str = ""
    #: Their evaluator's verdict, stored beside the attempt that produced it.
    #: Written while the image is still here, because afterwards it is not.
    verdict: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _docker(config: BenchConfig, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    """A docker command against the *sweep's* daemon.

    Never the host's. `DOCKER_HOST` is passed explicitly rather than exported,
    so nothing in this process can accidentally point the rest of it at the
    wrong daemon and start writing two hundred gigabytes to the system disk.
    """
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["docker", *args],
        env=config.docker_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def prepare(instance: Instance, config: BenchConfig) -> bool:
    """Pull the instance's evaluation image. Returns whether it is present."""
    image = config.image_for(instance.instance_id)
    if _docker(config, "image", "inspect", image).returncode == 0:
        return True
    log.info("bench: pulling %s", image)
    pulled = _docker(config, "pull", image, timeout=config.eval_timeout)
    if pulled.returncode != 0:
        log.warning("bench: cannot pull %s: %s", image, pulled.stderr.strip()[:200])
        return False
    return True


def read_sources(instance: Instance, config: BenchConfig) -> dict[str, str]:
    """The files the crash names, read out of the instance's own image.

    Read from the image rather than cloned from GitHub, because the image is
    what the evaluator will build and the repository at `base_commit` is only
    probably the same thing. One `docker run` per instance, not per file: the
    container start dominates, and a shell loop inside it is free.

    A path the report names but the image does not have is skipped. Reports come
    from a machine that laid the tree out differently, so a miss is ordinary --
    `candidate_paths` proposes and this is what disposes.
    """
    wanted = instance.crash_paths(depth=config.caller_depth)
    if not wanted:
        return {}

    # Each file delimited by a marker, so one exec returns all of them and a
    # missing file simply contributes nothing between two markers.
    script = "; ".join(
        f'if [ -f "{instance.work_dir}/{path}" ]; then '
        f'echo "===SECB:{path}==="; cat "{instance.work_dir}/{path}"; fi'
        for path in wanted
    )
    result = _docker(
        config,
        "run",
        "--rm",
        "--entrypoint",
        "/bin/sh",
        config.image_for(instance.instance_id),
        "-c",
        script,
        timeout=config.eval_timeout,
    )
    if result.returncode != 0:
        log.warning("bench: cannot read sources for %s: %s", instance.instance_id, result.stderr.strip()[:200])
        return {}
    return _split_marked(result.stdout)


def _split_marked(blob: str) -> dict[str, str]:
    files: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in blob.splitlines(keepends=True):
        marker = line.strip()
        if marker.startswith("===SECB:") and marker.endswith("==="):
            if current is not None:
                files[current] = "".join(body)
            current = marker[len("===SECB:") : -len("===")]
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        files[current] = "".join(body)
    return {path: text for path, text in files.items() if text.strip()}


def _patch_from(report: Report, sources: dict[str, str]) -> tuple[str, Finding | None, str]:
    """The best patch the report offers, as a unified diff.

    Findings are already sorted worst-first by `sorted_findings`, so this takes
    the most severe one that actually carries an applicable replacement. A
    finding whose fix could not be expressed as a line replacement is skipped
    rather than guessed at -- `remediate` deliberately leaves `replacement`
    empty when the change does not fit in place.
    """
    for finding in report.sorted_findings():
        original = sources.get(finding.primary.file)
        if original is None or not (finding.remediation.replacement or "").strip():
            continue
        try:
            patched = splice(original, finding.primary, finding.remediation.replacement or "")
        except Stale as err:
            log.debug("bench: %s not applicable: %s", finding.id, err)
            continue
        diff = unified_diff(finding.primary.file, original, patched)
        if diff:
            return diff, finding, ""
    if report.findings:
        return "", None, "찾았지만 그 자리에서 고칠 수 있는 패치가 나오지 않았습니다"
    return "", None, ""


def run_one(instance: Instance, config: BenchConfig, agent_config: AgentConfig | None = None) -> Attempt:
    """Inspect one instance and produce what it produced.

    Never raises for an instance's own failure. A sweep of two hundred that dies
    on the seventh is worse than one that records seven results and a reason --
    so anything that goes wrong here becomes a stage on the attempt.
    """
    attempt = Attempt(instance_id=instance.instance_id)
    agent_config = agent_config or AgentConfig()

    sources = read_sources(instance, config)
    if not sources:
        attempt.stage = "not_located"
        attempt.note = "크래시가 가리키는 파일을 이미지에서 찾지 못했습니다"
        return attempt
    attempt.shown = sorted(sources)

    run = new_run(agent_config)
    attempt.run_id = run.run_id
    write_files(run, {path: text.encode("utf-8") for path, text in sources.items()})
    store = run.store()
    try:
        build_index(sources, store)
        report = run_inspection(
            run_id=run.run_id,
            files=sources,
            store=store,
            config=agent_config,
            spans=run.spans(),
            # Every instance is its own tree, so there is nothing to reuse and a
            # warm read would only be confusing in the trace.
            warm=False,
        )
    except Exception as err:  # noqa: BLE001 - one instance failing is a result
        log.warning("bench: inspection failed for %s: %s", instance.instance_id, err)
        attempt.stage = "not_located"
        attempt.note = f"검사가 실패했습니다: {err}"
        return attempt
    finally:
        store.close()

    run.save_report(report)
    run.set_status("done")
    attempt.config_hash = run.read_meta().get("config_hash")

    patch, finding, note = _patch_from(report, sources)
    attempt.patch = patch
    attempt.note = note
    if finding is not None:
        attempt.finding_id = finding.id
        attempt.cwe = finding.cwe
    elif not report.findings:
        attempt.stage = "not_located"
        attempt.note = "크래시가 가리키는 파일에서 아무것도 보고하지 않았습니다"
    else:
        attempt.stage = "misread"
    return attempt


def sweep(instances: Sequence[Instance], config: BenchConfig, resume: bool = True) -> list[Attempt]:
    """Every instance, in order, writing as it goes.

    Written after each rather than at the end, and **resumable by default**: a
    sweep is measured in days, the machine it runs on is shared, and a crash at
    the hundred and ninetieth should cost one instance rather than the week. An
    instance with an `attempt.json` already on disk is skipped and its result
    carried forward, so re-running the same command continues rather than
    starting over.

    `resume=False` is how you ask for the work again -- a new model, say, where
    every previous answer is about a different system.
    """
    config.runs_dir.mkdir(parents=True, exist_ok=True)

    done = {attempt.instance_id: attempt for attempt in load_attempts(config)} if resume else {}
    attempts: list[Attempt] = []
    todo = [instance for instance in instances if instance.instance_id not in done]
    if done:
        log.info("bench: %d already done, %d to go", len(done), len(todo))

    for position, instance in enumerate(instances, start=1):
        carried = done.get(instance.instance_id)
        if carried is not None:
            attempts.append(carried)
            continue

        log.info("bench: [%d/%d] %s", position, len(instances), instance.instance_id)
        if not prepare(instance, config):
            attempts.append(
                Attempt(
                    instance_id=instance.instance_id,
                    stage="not_located",
                    note="평가 이미지를 받지 못했습니다",
                )
            )
        else:
            attempts.append(run_one(instance, config))

        # Scored here, before the image goes. The image is what the evaluator
        # builds in, so scoring at the end of the sweep -- which is what this
        # did -- meant every instance was downloaded once to run against and a
        # second time to be judged in. Two hundred of them at ~2.8GB is not a
        # rounding error.
        #
        # It also means the sweep reports as it goes. A run that takes days and
        # says nothing until it finishes is a run nobody can course-correct.
        verdict = _score_now(attempts[-1], config)
        if verdict is not None:
            attempts[-1].verdict = verdict

        _write_attempt(attempts[-1], config)
        # Rewritten every instance so an interrupted sweep still has a
        # `preds.json` covering everything that finished.
        write_predictions(attempts, config)

        if config.prune_after:
            # The reason is the volume: the full set is around two hundred
            # gigabytes on a disk shared with other accounts.
            _docker(config, "rmi", "-f", config.image_for(instance.instance_id))

    return attempts


def _score_now(attempt: Attempt, config: BenchConfig) -> dict | None:
    """Their evaluator, on this one instance, before its image is removed.

    Imported here rather than at module scope: `score` imports `Attempt` from
    this module, so a top-level import would close a cycle. Failure is a missing
    verdict rather than a dead sweep -- `outcome_for` renders that as not-yet
    -scored, and `agent bench score` can fill it in later from `preds.json`.
    """
    try:
        from .score import score_one

        return score_one(attempt, config)
    except Exception as err:  # noqa: BLE001 - one instance's scoring is not the sweep
        log.warning("bench: could not score %s: %s", attempt.instance_id, err)
        return None


def _write_attempt(attempt: Attempt, config: BenchConfig) -> None:
    target = config.runs_dir / attempt.instance_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "attempt.json").write_text(json.dumps(attempt.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    if attempt.patch:
        (target / "patch.diff").write_text(attempt.patch, encoding="utf-8")


def write_predictions(attempts: Sequence[Attempt], config: BenchConfig) -> None:
    """`preds.json`, in the shape SEC-bench's evaluator reads.

    SWE-agent's format -- `{instance_id: {model_patch: "..."}}` -- because it is
    the simplest of the four they accept and needs no change upstream. An
    instance with no patch is still written, with an empty string: their
    evaluator counts it as unresolved, which is exactly what it is, and dropping
    it would silently shrink the denominator.
    """
    config.predictions_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        attempt.instance_id: {"instance_id": attempt.instance_id, "model_patch": attempt.patch}
        for attempt in attempts
    }
    config.predictions_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_attempts(config: BenchConfig) -> list[Attempt]:
    """What a previous sweep wrote. Read by the surface and by `score`."""
    if not config.runs_dir.is_dir():
        return []
    found: list[Attempt] = []
    for path in sorted(config.runs_dir.glob("*/attempt.json")):
        try:
            found.append(Attempt(**json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, TypeError) as err:
            log.warning("bench: cannot read %s: %s", path, err)
    return found
