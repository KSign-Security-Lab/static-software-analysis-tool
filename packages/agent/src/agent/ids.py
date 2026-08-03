"""Stable, content-derived finding ids.

An id must survive things that do not change the finding -- the file being
edited above it, the chunk being reindented, the run being repeated -- and must
change when the finding itself is different. Positional ids fail the first test,
which is why they are not used: insert a line at the top of a file and every
finding below it would appear "new".

Because the id is content-derived, two reports of the same tree can be diffed
into new / fixed / unchanged, which is what the git-diff framing in the UI
actually rests on.
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")

#: Tolerates the separators models use: ``CWE-78``, ``CWE 78``, ``CWE_78``, and
#: the U+2011 non-breaking hyphen that turns up in copied documentation.
_CWE = re.compile(r"CWE[\s\-_‐-―]*(\d{1,4})", re.IGNORECASE)


def normalize_cwe(raw: str | None) -> str | None:
    """Reduce whatever the model said to a canonical ``CWE-nnn``, or None.

    Constrained decoding fixes a field's *type*, not its discipline. A real run
    returned a whole markdown paragraph -- two CWE references, prose, and
    mitre.org links -- in this field, which then rendered as the marker's source
    label in the editor.

    Rejecting the finding over it would be disproportionate: the analysis was
    correct and the identifier was in there. So the first CWE number wins and
    the rest is discarded. A value with no CWE number at all becomes None,
    because a made-up identifier is worse than none.
    """
    if not raw:
        return None
    match = _CWE.search(raw)
    return f"CWE-{int(match.group(1))}" if match else None


def normalize_anchor(text: str) -> str:
    """Canonical form of an anchor, for hashing and matching.

    Whitespace is collapsed so reformatting does not change the id, and case is
    preserved because identifiers are case-sensitive in every language indexed.
    """
    return _WHITESPACE.sub(" ", text).strip()


def finding_id(*, file: str, symbol: str, cwe: str | None, anchor_text: str) -> str:
    """Stable id for a finding.

    Keyed on the enclosing *symbol* rather than the line number, so edits
    elsewhere in the file do not renumber it. Two genuinely different findings
    on the same anchor are distinguished by their CWE; two findings with the
    same CWE on the same anchor in the same function are the same finding, which
    is the intended collapse.
    """
    material = "\x00".join([file, symbol, cwe or "", normalize_anchor(anchor_text)])
    return hashlib.sha256(material.encode()).hexdigest()[:16]
