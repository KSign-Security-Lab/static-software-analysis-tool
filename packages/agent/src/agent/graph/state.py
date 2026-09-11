from __future__ import annotations

from typing import Annotated, Any, TypedDict

RESET = "__reset__"


def concat(old: list[Any], new: list[Any] | str) -> list[Any]:
    if isinstance(new, str):
        return []
    return [*old, *new]


def merge(old: dict[str, Any], new: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(new, str):
        return {}
    return {**old, **new}


def add_counts(old: dict[str, int], new: dict[str, int] | str) -> dict[str, int]:
    if isinstance(new, str):
        return {}
    merged = dict(old)
    for key, value in new.items():
        merged[key] = merged.get(key, 0) + value
    return merged


class InspectionState(TypedDict, total=False):
    pending: list[str]
    wave: list[str]
    current: str | None
    packs: Annotated[dict[str, str], merge]
    confirmed: Annotated[list[dict[str, Any]], concat]
    stats: Annotated[dict[str, int], add_counts]


# One chunk's own pipeline. The accumulators that used to be wave-wide live here, so
# they are bounded by the chunk rather than cleared by the next round.
class ChunkState(TypedDict, total=False):
    chunk_id: str
    triaged: Annotated[dict[str, Any], merge]
    scouted: Annotated[dict[str, Any], merge]
    candidates: Annotated[list[dict[str, Any]], concat]
    located: Annotated[list[dict[str, Any]], concat]
    verdicts: Annotated[list[dict[str, Any]], concat]
    confirmed: Annotated[list[dict[str, Any]], concat]
    stats: Annotated[dict[str, int], add_counts]


WAVE_CHANNELS = ("packs", "confirmed")


def clear_wave() -> dict[str, Any]:
    return {channel: RESET for channel in WAVE_CHANNELS}


def initial_state(order: list[str], chunks_total: int, stats: dict[str, int] | None = None) -> InspectionState:
    base = {
        "files_indexed": 0,
        "files_skipped": 0,
        "chunks_total": chunks_total,
        "chunks_inspected": 0,
        "chunks_cached": 0,
        "candidates": 0,
        "dropped_unlocatable": 0,
        "refuted": 0,
        "triaged_out": 0,
        "regions": 0,
    }
    if stats:
        base.update(stats)
    return InspectionState(
        pending=list(order),
        wave=[],
        current=None,
        packs={},
        confirmed=[],
        stats=base,
    )
