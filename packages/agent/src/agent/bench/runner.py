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
    instance_id: str
    run_id: str | None = None
    config_hash: str | None = None
    shown: list[str] | None = None
    patch: str = ""
    finding_id: str | None = None
    cwe: str | None = None
    stage: str = ""
    note: str = ""
    verdict: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _docker(config: BenchConfig, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["docker", *args],
        env=config.docker_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def prepare(instance: Instance, config: BenchConfig) -> bool:
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
    wanted = instance.crash_candidates(depth=config.caller_depth)
    if not wanted:
        return {}

    script = "; ".join(
        " ".join(
            f'{"if" if position == 0 else "elif"} [ -f "{instance.work_dir}/{path}" ]; then '
            f'echo "===SECB:{path}==="; cat "{instance.work_dir}/{path}";'
            for position, path in enumerate(readings)
        )
        + " fi"
        for readings in wanted
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
    attempt = Attempt(instance_id=instance.instance_id)
    agent_config = agent_config or AgentConfig()
    sources = read_sources(instance, config)
    if not sources:
        attempt.stage = "harness_error"
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
            warm=False,
        )
    except Exception as err:  # noqa: BLE001 - one instance failing is a result
        log.warning("bench: inspection failed for %s: %s", instance.instance_id, err)
        attempt.stage = "harness_error"
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
                    stage="harness_error",
                    note="평가 이미지를 받지 못했습니다",
                )
            )
        else:
            attempts.append(run_one(instance, config))

        verdict = _score_now(attempts[-1], config)
        if verdict is not None:
            attempts[-1].verdict = verdict

        _write_attempt(attempts[-1], config)
        write_predictions(attempts, config)

        if config.prune_after:
            _prune(instance.instance_id, config)

    return attempts


def _prune(instance_id: str, config: BenchConfig) -> None:
    _docker(config, "rmi", "-f", config.image_for(instance_id))

    listed = _docker(
        config, "images", "--format", "{{.Repository}}:{{.Tag}}", "--filter", f"reference=*{instance_id}*"
    )
    for reference in dict.fromkeys((listed.stdout or "").split()):
        _docker(config, "rmi", "-f", reference)

    _docker(config, "container", "prune", "-f")
    _docker(config, "image", "prune", "-f")
    _docker(config, "builder", "prune", "-f")


def _score_now(attempt: Attempt, config: BenchConfig) -> dict | None:
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
    config.predictions_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        attempt.instance_id: {"instance_id": attempt.instance_id, "model_patch": attempt.patch}
        for attempt in attempts
    }
    config.predictions_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_attempts(config: BenchConfig) -> list[Attempt]:
    if not config.runs_dir.is_dir():
        return []
    found: list[Attempt] = []
    for path in sorted(config.runs_dir.glob("*/attempt.json")):
        try:
            found.append(Attempt(**json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, TypeError) as err:
            log.warning("bench: cannot read %s: %s", path, err)
    return found
