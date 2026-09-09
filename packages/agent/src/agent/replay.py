from __future__ import annotations

import logging
from typing import Any, Callable

from .config import AgentConfig
from .harness import apply_to, load
from .schema import Report

log = logging.getLogger(__name__)
METRICS: dict[str, Callable[[Report], float]] = {
    "confirmed_per_call": lambda r: (
        sum(1 for f in r.findings if f.verified) / r.stats.chunks_inspected
        if r.stats.chunks_inspected
        else 0.0
    ),
    "confirmed": lambda r: float(sum(1 for f in r.findings if f.verified)),
    "chunks_inspected": lambda r: float(r.stats.chunks_inspected),
    "findings": lambda r: float(len(r.findings)),
    "refuted": lambda r: float(r.stats.refuted),
}


def measure(report: Report, metric: str) -> float:
    read = METRICS.get(metric)
    if read is None:
        raise ValueError(f"unknown metric {metric!r}; expected one of {', '.join(sorted(METRICS))}")
    return float(read(report))


def improved(before: float, after: float, direction: str) -> bool:
    return after > before if direction == "up" else after < before


def compare(
    *,
    base_hash: str,
    proposed_hash: str,
    metric: str,
    direction: str,
    run_arm: Callable[[AgentConfig, str], Report],
    corpus: str,
    config: AgentConfig | None = None,
) -> dict[str, Any]:
    base = load(base_hash, config)
    proposed = load(proposed_hash, config)
    if base is None or proposed is None:
        raise ValueError("both configs must be recorded before they can be replayed")

    settings = config or AgentConfig()
    before_report = run_arm(apply_to(settings, base.knobs), corpus)
    after_report = run_arm(apply_to(settings, proposed.knobs), corpus)
    before = measure(before_report, metric)
    after = measure(after_report, metric)
    verdict = improved(before, after, direction)

    log.info(
        "replay over %s: %s %.4f -> %.4f (%s) -> %s",
        corpus,
        metric,
        before,
        after,
        direction,
        "improved" if verdict else "not improved",
    )
    return {
        "corpus": corpus,
        "metric": metric,
        "direction": direction,
        "base_hash": base_hash,
        "proposed_hash": proposed_hash,
        "before": before,
        "after": after,
        "improved": verdict,
        "base_stats": before_report.stats.model_dump(),
        "proposed_stats": after_report.stats.model_dump(),
    }
