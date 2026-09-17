from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from .prompts import (
    GATHER_SYSTEM,
    LENS_SYSTEM,
    REPLAN_SYSTEM,
    SCOUT_SYSTEM,
    TRIAGE_SYSTEM,
    VERIFY_SYSTEM,
)
from .remediate import FIX_SYSTEM
from .schema import Lens

log = logging.getLogger(__name__)


def lens_prompt(lens: Lens) -> str:
    return f"lens:{lens}"


DEFAULTS: dict[str, str] = {
    "triage": TRIAGE_SYSTEM,
    "scout": SCOUT_SYSTEM,
    **{lens_prompt(lens): text for lens, text in LENS_SYSTEM.items()},
    "gather": GATHER_SYSTEM,
    "verify": VERIFY_SYSTEM,
    "replan": REPLAN_SYSTEM,
    "fix": FIX_SYSTEM,
}

NAMES = tuple(DEFAULTS)


class UnknownPrompt(KeyError):
    pass


def _check(name: str) -> str:
    if name not in DEFAULTS:
        raise UnknownPrompt(f"unknown prompt: {name!r}; expected one of {', '.join(NAMES)}")
    return name


def load(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        log.warning("ignoring unreadable prompt overrides at %s", path)
        return {}
    if not isinstance(raw, dict):
        return {}
    return {name: text for name, text in raw.items() if name in DEFAULTS and isinstance(text, str) and text.strip()}


def resolve(path: Path, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    resolved = dict(DEFAULTS)
    resolved.update(overrides if overrides is not None else load(path))
    return resolved


def save(path: Path, name: str, text: str) -> dict[str, str]:
    _check(name)
    if not text.strip():
        raise ValueError(f"{name} prompt is empty; use clear() to go back to the default")

    overrides = load(path)
    overrides[name] = text
    _write(path, overrides)
    return overrides


def clear(path: Path, name: str) -> dict[str, str]:
    _check(name)
    overrides = load(path)
    overrides.pop(name, None)
    _write(path, overrides)
    return overrides


def _write(path: Path, overrides: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")


def describe(path: Path) -> list[dict[str, Any]]:
    overrides = load(path)
    return [
        {
            "name": name,
            "default": DEFAULTS[name],
            "override": overrides.get(name),
            "in_use": overrides.get(name, DEFAULTS[name]),
        }
        for name in NAMES
    ]
