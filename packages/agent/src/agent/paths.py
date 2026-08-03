"""Run-root confinement.

Every path that reaches a filesystem tool passes through :func:`resolve_within`.
The input is an uploaded archive of arbitrary content, so this is a real
boundary rather than a formality: an entry named ``../../etc/passwd``, an
absolute path, or a symlink pointing out of the tree must all be rejected.

Resolution is done with ``Path.resolve()`` on the *combined* path and then
checked against the resolved root, which is what makes symlink escapes fail --
a lexical check on the string would pass them.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class PathEscape(ValueError):
    """A path pointed outside the run root."""


def resolve_within(root: Path, candidate: str) -> Path:
    """Resolve ``candidate`` under ``root``, or raise :class:`PathEscape`.

    Absolute inputs are rejected rather than silently reinterpreted: a tool
    asked for ``/etc/passwd`` has been given a path it should not have, and
    quietly serving ``<root>/etc/passwd`` would hide that.
    """
    pure = PurePosixPath(candidate)
    if pure.is_absolute() or candidate.startswith("\\"):
        raise PathEscape(f"absolute paths are not allowed: {candidate!r}")
    if any(part == ".." for part in pure.parts):
        raise PathEscape(f"path escapes the run root: {candidate!r}")

    resolved_root = root.resolve()
    resolved = (resolved_root / pure).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise PathEscape(f"path escapes the run root: {candidate!r}")
    return resolved


def is_within(root: Path, path: Path) -> bool:
    """True if ``path`` resolves inside ``root``. Follows symlinks."""
    try:
        resolved_root = root.resolve()
        resolved = path.resolve()
    except OSError:
        return False
    return resolved == resolved_root or resolved_root in resolved.parents


def relative_to_root(root: Path, path: Path) -> str:
    """POSIX path relative to the run root -- the only form used on the wire."""
    return str(PurePosixPath(*path.resolve().relative_to(root.resolve()).parts))
