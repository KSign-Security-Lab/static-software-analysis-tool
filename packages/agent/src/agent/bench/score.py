"""Scoring, by SEC-bench's evaluator rather than by ours.

Whether a patch builds, silences the sanitizer and leaves the tests passing is
the one number this whole exercise produces, and it is the number that has to be
trustworthy. Reimplementing their harness would make it ours -- a figure we
computed about ourselves, against a benchmark whose value is that we did not.

So this drives `secb.evaluator.eval_instances` inside the pinned `secbench`
image, on the sweep's own daemon, and reads what it wrote. The only judgement
here is turning their per-instance verdict into the taxonomy the surface groups
by, and that mapping is written down below rather than inferred.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from .config import BenchConfig
from .runner import Attempt

log = logging.getLogger(__name__)

#: Their verdict to our stage.
#:
#: The three patch stages exist because "it did not work" is four different
#: problems: a patch that will not compile is a different fix from one that
#: compiles and does not help, which is different again from one that helps and
#: breaks something else. Collapsing them would leave the page saying "unresolved"
#: and pointing at nothing.
_STAGE_FOR = {
    "build_failed": "patch_build_failed",
    "not_fixed": "built_not_fixed",
    "tests_failed": "fixed_tests_broke",
}


def score(attempts: list[Attempt], config: BenchConfig) -> dict[str, dict[str, Any]]:
    """Run their evaluator over `preds.json` and return a verdict per instance.

    Instances the runner never got a patch out of are still passed through: they
    are unresolved, which is a result, and dropping them would shrink the
    denominator without saying so.
    """
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
    """Whatever the evaluator left in `results/`, keyed by instance.

    Tolerant on purpose. Their report's exact filename and shape are theirs to
    change, and a sweep that lost a day's work because a key was renamed would
    be worse than one that reports what it could read -- so this looks for the
    fields it needs wherever they are and says so when they are absent.
    """
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
    """`{id: {...}}` and `[{instance_id: ..., ...}]` both happen in the wild."""
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
    """`(outcome, note)` for one instance, as the surface groups them.

    The runner owns the early stages and the evaluator owns the late ones, which
    is the honest division: only the runner knows whether the agent found
    anything, and only a build knows whether the patch works.
    """
    if attempt.stage:
        return attempt.stage, attempt.note
    if not attempt.patch:
        return "not_located", attempt.note or "패치를 내놓지 않았습니다"
    if verdict is None:
        return "not_run", "아직 채점하지 않았습니다"

    if verdict.get("resolved") is True:
        return "solved", ""

    for key in ("stage", "failure", "reason", "status"):
        raw = str(verdict.get(key) or "")
        for needle, stage in _STAGE_FOR.items():
            if needle in raw:
                return stage, raw
    # Scored, not resolved, and their report did not say which way it failed.
    # `built_not_fixed` is the middle of the three and the least wrong guess --
    # and the note carries what they actually said so nobody has to trust it.
    return "built_not_fixed", json.dumps(verdict, ensure_ascii=False)[:200]
