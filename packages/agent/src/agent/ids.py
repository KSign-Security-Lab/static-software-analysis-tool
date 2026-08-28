"""Stable, content-derived finding ids."""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")

# Tolerates CWE-78, CWE 78, CWE_78 and the U+2011 hyphen from copied docs.
_CWE = re.compile(r"CWE[\s\-_‐-―]*(\d{1,4})", re.IGNORECASE)


def normalize_anchor(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def normalize_cwe(raw: str | None) -> str | None:
    """First CWE number in ``raw``, canonicalised, or None.

    Constrained decoding fixes the field's type, not its discipline: a real run
    returned a markdown paragraph with two CWE links here.
    """
    if not raw:
        return None
    match = _CWE.search(raw)
    return f"CWE-{int(match.group(1))}" if match else None


def finding_id(*, file: str, symbol: str, cwe: str | None, anchor_text: str) -> str:
    """Keyed on the enclosing symbol, not the line, so edits above a finding do
    not make it look new. That is what makes run-to-run diffing work."""
    material = "\x00".join([file, symbol, cwe or "", normalize_anchor(anchor_text)])
    return hashlib.sha256(material.encode()).hexdigest()[:16]
