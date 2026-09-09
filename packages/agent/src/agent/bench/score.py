from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from .config import BenchConfig
from .runner import Attempt

log = logging.getLogger(__name__)
_STAGE_FOR = {
    "build_failed": "patch_build_failed",
    "not_fixed": "built_not_fixed",
    "tests_failed": "fixed_tests_broke",
}


def score(attempts: list[Attempt], config: BenchConfig) -> dict[str, dict[str, Any]]:
    config.results_dir.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            "docker",
            "compose",
            "--profile",
            "secbench",
            "exec",
            "-T",
            "secbench",
            "python",
            "-m",
            "secb.evaluator.eval_instances",
            "--input-dir",
            "/secbench",
            "--type",
            "patch",
            "--split",
            config.split,
            "--agent",
            "swea",
            "--num-workers",
            str(config.workers),
            "--output-dir",
            "/secbench/results",
        ],
        capture_output=True,
        text=True,
        timeout=config.eval_timeout * max(1, len(attempts)),
        check=False,
    )
    if completed.returncode != 0:
        log.error("bench: evaluator exited %d: %s", completed.returncode, completed.stderr.strip()[-800:])

    return read_results(config)


def read_results(config: BenchConfig) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not config.results_dir.is_dir():
        return found

    for path in sorted(config.results_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for instance_id, verdict in _rows(payload):
            found[instance_id] = verdict
    return found


def _rows(payload: Any) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(payload, dict):
        if "instance_id" in payload:
            return [(str(payload["instance_id"]), payload)]
        return [(str(key), value) for key, value in payload.items() if isinstance(value, dict)]
    if isinstance(payload, list):
        return [
            (str(item["instance_id"]), item)
            for item in payload
            if isinstance(item, dict) and item.get("instance_id")
        ]
    return []


def outcome_for(attempt: Attempt, verdict: dict[str, Any] | None) -> tuple[str, str]:
    if attempt.stage:
        return attempt.stage, attempt.note
    if not attempt.patch:
        return "not_located", attempt.note or "패치를 내놓지 않았습니다"
    if verdict is None:
        return "awaiting_score", "패치는 나왔고 아직 채점되지 않았습니다"

    if verdict.get("resolved") is True:
        return "solved", ""

    for key in ("stage", "failure", "reason", "status"):
        raw = str(verdict.get(key) or "")
        for needle, stage in _STAGE_FOR.items():
            if needle in raw:
                return stage, raw
    return "built_not_fixed", json.dumps(verdict, ensure_ascii=False)[:200]


def score_one(attempt: Attempt, config: BenchConfig) -> dict[str, Any] | None:
    if not attempt.patch:
        return None

    one = config.results_dir / "single" / attempt.instance_id
    one.mkdir(parents=True, exist_ok=True)
    (one / "preds.json").write_text(
        json.dumps({attempt.instance_id: {"instance_id": attempt.instance_id, "model_patch": attempt.patch}}, indent=2),
        encoding="utf-8",
    )

    inside = f"/secbench/results/single/{attempt.instance_id}"
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            "docker", "compose", "--profile", "secbench", "exec", "-T", "secbench",
            "python", "-m", "secb.evaluator.eval_instances",
            "--input-dir", inside,
            "--type", "patch",
            "--split", config.split,
            "--agent", "swea",
            "--num-workers", "1",
            "--output-dir", inside,
        ],
        capture_output=True,
        text=True,
        timeout=config.eval_timeout,
        check=False,
    )
    if completed.returncode != 0:
        log.warning("bench: scoring %s exited %d: %s", attempt.instance_id, completed.returncode, completed.stderr.strip()[-400:])

    for path in sorted(one.rglob("*.json")):
        if path.name == "preds.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for instance_id, verdict in _rows(payload):
            if instance_id == attempt.instance_id:
                return verdict
    return None
