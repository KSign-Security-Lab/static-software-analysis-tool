from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")
_CWE = re.compile(r"CWE[\s\-_‐-―]*(\d{1,4})", re.IGNORECASE)


def normalize_anchor(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def normalize_cwe(raw: str | None) -> str | None:
    if not raw:
        return None
    match = _CWE.search(raw)
    return f"CWE-{int(match.group(1))}" if match else None


def finding_id(*, file: str, symbol: str, cwe: str | None, anchor_text: str) -> str:
    material = "\x00".join([file, symbol, cwe or "", normalize_anchor(anchor_text)])
    return hashlib.sha256(material.encode()).hexdigest()[:16]
