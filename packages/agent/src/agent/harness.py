from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .config import AgentConfig
from .db import HarnessConfig, ensure, session_factory

log = logging.getLogger(__name__)
FORMAT = "1"
TUNABLE: tuple[str, ...] = (
    "model",
    "lenses",
    "triage",
    "planning",
    "context_char_budget",
    "max_chunk_chars",
    "max_callee_notes",
    "max_verify_per_chunk",
    "wave_width",
    "max_tool_calls",
    "max_lens_tool_calls",
    "lens_tools",
    "enable_tools",
    "max_tokens",
    "reasoning_effort",
)


def knobs(config: AgentConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in sorted(TUNABLE):
        value = getattr(config, name)
        out[name] = sorted(value) if isinstance(value, tuple) else value
    return out


def fingerprint(config: AgentConfig) -> str:
    material = json.dumps({"format": FORMAT, "knobs": knobs(config)}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Recorded:
    config_hash: str
    knobs: dict[str, Any]
    pinned: bool
    label: str


def record(config: AgentConfig, label: str = "") -> str:
    ensure()
    digest = fingerprint(config)
    with session_factory(config)() as session:
        session.execute(
            insert(HarnessConfig)
            .values(config_hash=digest, knobs=knobs(config), label=label, pinned=False)
            .on_conflict_do_nothing()
        )
        session.commit()
    return digest


def load(config_hash: str, config: AgentConfig | None = None) -> Recorded | None:
    with session_factory(config)() as session:
        row = session.get(HarnessConfig, config_hash)
        if row is None:
            return None
        return Recorded(
            config_hash=row.config_hash,
            knobs=dict(row.knobs or {}),
            pinned=bool(row.pinned),
            label=row.label or "",
        )


def pin(config_hash: str, pinned: bool = True, config: AgentConfig | None = None) -> bool:
    with session_factory(config)() as session:
        row = session.get(HarnessConfig, config_hash)
        if row is None:
            return False
        row.pinned = pinned
        session.commit()
    return True


def all_configs(config: AgentConfig | None = None) -> list[Recorded]:
    with session_factory(config)() as session:
        rows = session.scalars(select(HarnessConfig).order_by(HarnessConfig.created_at)).all()
    return [
        Recorded(
            config_hash=row.config_hash,
            knobs=dict(row.knobs or {}),
            pinned=bool(row.pinned),
            label=row.label or "",
        )
        for row in rows
    ]


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, tuple[Any, Any]]:
    changed: dict[str, tuple[Any, Any]] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old != new:
            changed[key] = (old, new)
    return changed


def apply_to(config: AgentConfig, changes: Mapping[str, Any]) -> AgentConfig:
    from dataclasses import replace

    honoured = {key: value for key, value in changes.items() if key in TUNABLE}
    if "lenses" in honoured and not isinstance(honoured["lenses"], tuple):
        honoured["lenses"] = tuple(honoured["lenses"])
    return replace(config, **honoured)
