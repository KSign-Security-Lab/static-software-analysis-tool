"""A/B replay: running a proposed config against the one it would replace.

The only thing that turns a tuner's observation into a permitted change. The
evidence a proposal carries is about runs that already happened -- this lens
raised nothing, these runs stopped short of their queue -- and the change it
asks for is a claim about runs that have not. Nothing in the recorded past
settles that. A run with the change in does.

Over a *pinned* corpus, and pinned is the whole of it: a replay against whatever
happened to be lying around measures the corpus as much as the config, and two
configs judged on different trees are not being compared. The corpus is named,
the same files go to both arms, and the arms differ in exactly the knobs the
proposal names.

The comparison is deliberately coarse -- one metric, one direction, stated by
the proposal before the replay runs. A replay that could pick its own metric
afterwards would approve everything, because some number always moves.

Kept apart from `tuner.py` so the thing that scores an experiment is not the
thing that proposed it. `tuner.attach_replay` takes this module's report and is
not allowed to compute one.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .config import AgentConfig
from .harness import apply_to, load
from .schema import Report

log = logging.getLogger(__name__)

#: What each metric is read from. A proposal names one of these and a direction
#: before it is replayed, so the answer cannot be chosen after the fact.
METRICS: dict[str, Callable[[Report], float]] = {
    # Claims that survived the refute pass, per unit inspected. The default
    # because it moves the wrong way for the two failures that matter: a config
    # that finds less, and one that spends more to find the same.
    "confirmed_per_call": lambda r: (
        sum(1 for f in r.findings if f.verified) / r.stats.chunks_inspected
        if r.stats.chunks_inspected
        else 0.0
    ),
    "confirmed": lambda r: float(sum(1 for f in r.findings if f.verified)),
    "chunks_inspected": lambda r: float(r.stats.chunks_inspected),
    "findings": lambda r: float(len(r.findings)),
    # Lower is better for this one, which is why `direction` is part of the
    # proposal rather than assumed.
    "refuted": lambda r: float(r.stats.refuted),
}


def measure(report: Report, metric: str) -> float:
    read = METRICS.get(metric)
    if read is None:
        raise ValueError(f"unknown metric {metric!r}; expected one of {', '.join(sorted(METRICS))}")
    return float(read(report))


def improved(before: float, after: float, direction: str) -> bool:
    """Whether the metric moved the way the proposal said it would.

    Ties are failures. A change that did nothing measurable is a change with no
    argument for it, and the default has to be to leave the harness alone.
    """
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
    """Run both arms over one pinned corpus and report which way the metric went.

    `run_arm` is injected rather than called directly here, and that is not
    ceremony: a replay costs two full inspections, and the caller owns whether
    those are live model calls, a cached corpus or a fixture. This module owns
    the *comparison*, which is the part that has to be trustworthy.

    The returned dict is what `tuner.attach_replay` stores verbatim, so the
    numbers behind an approval stay readable long after the run has gone.
    """
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
        # Kept so a reader can see what each arm actually produced rather than
        # only the one number that decided it.
        "base_stats": before_report.stats.model_dump(),
        "proposed_stats": after_report.stats.model_dump(),
    }
