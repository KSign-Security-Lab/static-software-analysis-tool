"""Run-root confinement. The input is an arbitrary uploaded archive, so this is
a real boundary. Resolution happens on the combined path and is then checked
against the resolved root, which is what catches symlink escapes -- a lexical
check on the string would pass them."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class PathEscape(ValueError):
    """A path pointed outside the run root."""


def resolve_within(root: Path, candidate: str) -> Path:
    """Resolve under ``root`` or raise. Absolute inputs are rejected rather than
    reinterpreted -- quietly serving ``<root>/etc/passwd`` would hide the bug."""
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
