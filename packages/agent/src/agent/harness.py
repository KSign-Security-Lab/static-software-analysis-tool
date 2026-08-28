"""The harness config as a value: hashed, versioned, and never thrown away.

The system already measures itself. Verdicts refute by default, every call is a
span, a run resumes from its own checkpoints -- and none of it ever changed the
harness. There was no return path, and the reason is smaller than it sounds:
nothing recorded *which* configuration produced a result, so no measurement
could be attributed to a setting, and a change nobody can attribute is a change
nobody can defend.

So the knobs that already exist become a value with an identity. `fingerprint`
hashes the ones that change what a run does; the hash goes on the run row; a
finding can be traced to the exact configuration that found it. Everything the
tuner later does rests on that one property, which is why it is here on its own
and why `tuner.py` is not allowed to exist without it.

What is hashed is deliberately narrow. `base_url`, `api_key`, timeouts and
concurrency are not in it: they change how fast a run goes and not what it
concludes, and folding them in would make two identical analyses look like two
different configurations every time somebody moved a port. What *is* in it is
the set that decides the answer -- which specialists run, how much context they
get, how strictly a claim is judged, how far the run may walk.

Archived, never deleted. A superseded config stays reachable because the runs it
produced still point at it, and a hash that resolves to nothing is a result with
no provenance -- which is the failure this whole file exists to prevent.
"""

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

#: Bumped when the *set* of hashed knobs changes shape, so a hash computed under
#: an older definition is not mistaken for one computed under this one. Two
#: configs that differ only in a field this version does not know about would
#: otherwise collide, and a collision here is a result attributed to the wrong
#: settings.
FORMAT = "1"

#: The knobs that change what a run concludes, and therefore what it is fair to
#: compare. Anything not in here is either performance (timeouts, concurrency),
#: addressing (base_url, database_url), or bookkeeping.
#:
#: `model` is in it and `api_key` is not, which is the line: the model decides
#: the answer, the credential decides whether you get one.
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
    """The tunable settings of one config, JSON-shaped and ordered."""
    out: dict[str, Any] = {}
    for name in sorted(TUNABLE):
        value = getattr(config, name)
        out[name] = sorted(value) if isinstance(value, tuple) else value
    return out


def fingerprint(config: AgentConfig) -> str:
    """The identity of a harness configuration.

    Content-derived for the same reason a chunk id is: two runs configured the
    same way should be recognisably the same experiment without anyone having
    remembered to label them.
    """
    material = json.dumps({"format": FORMAT, "knobs": knobs(config)}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Recorded:
    """A config as stored: its hash, its knobs, and whether it is pinned."""

    config_hash: str
    knobs: dict[str, Any]
    pinned: bool
    label: str


def record(config: AgentConfig, label: str = "") -> str:
    """Write a config down if it is new, and return its hash.

    Idempotent by construction -- the hash *is* the key -- so a thousand runs
    under one configuration write one row and a thousand references to it.
    """
    # The first write of a run, and the first that touches a table added after
    # this database was built. See `db/schema.ensure`.
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
    """One recorded config, or None. The other half of traceability."""
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
    """Mark a config exempt from automatic proposals.

    A pin is a statement that this configuration is not to be argued with -- a
    baseline someone is measuring against, or a setting chosen for a reason the
    tuner cannot see. `tuner.propose` skips it, and that is checked there rather
    than trusted here.
    """
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
    """What changed between two knob sets. The shape a proposal is written in."""
    changed: dict[str, tuple[Any, Any]] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old != new:
            changed[key] = (old, new)
    return changed


def apply_to(config: AgentConfig, changes: Mapping[str, Any]) -> AgentConfig:
    """A copy of `config` with `changes` written over it.

    Only tunable keys are honoured. A proposal naming something outside
    :data:`TUNABLE` is proposing a change to how the run is *addressed* rather
    than to what it concludes, and the whole point of the set is that those are
    different questions.
    """
    from dataclasses import replace

    honoured = {key: value for key, value in changes.items() if key in TUNABLE}
    if "lenses" in honoured and not isinstance(honoured["lenses"], tuple):
        honoured["lenses"] = tuple(honoured["lenses"])
    return replace(config, **honoured)
