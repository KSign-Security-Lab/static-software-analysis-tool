"""Tuned system prompts, read at run time.

``prompts.py`` holds the defaults, in git, where they can be reviewed and
blamed. Tuning one against a real trace writes an override here instead of
editing that file: the default stays one click away, and a prompt saved from a
browser never turns up as an unexplained change to tracked source.

An override is keyed by the same ``step`` a span's metadata carries -- triage,
``lens:memory``, gather, verify -- which is what lets a row in the trace be
traced back to the prompt that produced it, and edited from there.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from .prompts import GATHER_SYSTEM, LENS_SYSTEM, SCOUT_SYSTEM, TRIAGE_SYSTEM, VERIFY_SYSTEM
from .remediate import FIX_SYSTEM
from .schema import Lens

log = logging.getLogger(__name__)


def lens_prompt(lens: Lens) -> str:
    """The prompt key for one specialist. Also the ``step`` its spans carry."""
    return f"lens:{lens}"


#: The system prompt behind each kind of model call. Every specialist is its own
#: entry, so a lens that is too eager can be reined in without touching the
#: other three -- which is the whole reason for splitting them up.
DEFAULTS: dict[str, str] = {
    "triage": TRIAGE_SYSTEM,
    "scout": SCOUT_SYSTEM,
    **{lens_prompt(lens): text for lens, text in LENS_SYSTEM.items()},
    "gather": GATHER_SYSTEM,
    "verify": VERIFY_SYSTEM,
    "fix": FIX_SYSTEM,
}

NAMES = tuple(DEFAULTS)


class UnknownPrompt(KeyError):
    """No such prompt. Saving under a typo would be a silent no-op."""


def _check(name: str) -> str:
    if name not in DEFAULTS:
        raise UnknownPrompt(f"unknown prompt: {name!r}; expected one of {', '.join(NAMES)}")
    return name


def load(path: Path) -> dict[str, str]:
    """Whatever has been deliberately overridden. Absent or corrupt reads empty.

    A malformed file must not stop the agent: falling back to the defaults gives
    a run that behaves as shipped, which is a far better failure than refusing
    to start.
    """
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
    """The prompts a run should actually use: defaults, shadowed by overrides."""
    resolved = dict(DEFAULTS)
    resolved.update(overrides if overrides is not None else load(path))
    return resolved


def save(path: Path, name: str, text: str) -> dict[str, str]:
    """Record an override. Returns what is overridden afterwards.

    An empty prompt is refused rather than stored: it is far more likely to be a
    cleared textarea than a deliberate instruction to say nothing, and the run it
    would produce is unexplainable.
    """
    _check(name)
    if not text.strip():
        raise ValueError(f"{name} prompt is empty; use clear() to go back to the default")

    overrides = load(path)
    overrides[name] = text
    _write(path, overrides)
    return overrides


def clear(path: Path, name: str) -> dict[str, str]:
    """Drop an override, putting the shipped default back."""
    _check(name)
    overrides = load(path)
    overrides.pop(name, None)
    _write(path, overrides)
    return overrides


def _write(path: Path, overrides: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")


def describe(path: Path) -> list[dict[str, Any]]:
    """Every prompt, its default, and what it has been changed to.

    Both are returned so the editor can offer a revert and a diff without a
    second request -- and so "this is the shipped one" is visible rather than
    inferred from the absence of a field.
    """
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
