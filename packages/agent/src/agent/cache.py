"""Analysis results, kept across runs.

A chunk id is derived from the file, the symbol and the normalised body, so an
unchanged function has the same id for ever. Within a run that already buys
something -- `chunks_cached` -- but across runs it bought nothing: uploading the
same tree twice, or re-inspecting after fixing one function, paid the full price
for every unit that had not moved. On a real codebase that is almost all of them.

What makes this safe is the recipe. Results are only ever reused for the exact
conditions that produced them: the same model, the same specialists, the same
prompts. Serving a result produced by a narrower configuration would be a false
negative that looks like a cache hit, which is the worst failure a tool like this
has -- so the recipe is part of the key rather than something checked afterwards
and warned about.

Beside the runs rather than inside one, because the whole point is that it
outlives the run that filled it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .index.store import ChunkStore

log = logging.getLogger(__name__)

#: Bumped when what is stored changes shape. An old row under a new format is
#: not a hit, which is cheaper than migrating something entirely rebuildable.
FORMAT = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    chunk_id TEXT NOT NULL,
    recipe   TEXT NOT NULL,
    findings TEXT NOT NULL,
    note     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (chunk_id, recipe)
);
"""


def recipe_of(*, model: str, lenses: Sequence[str], prompts: Mapping[str, str]) -> str:
    """What a result depends on, besides the code.

    Everything here changes the answer, so everything here changes the key. The
    prompts especially: tuning one from the studio is how a run is *meant* to
    produce different findings for the same code, and a cache that ignored that
    would quietly serve the old ones for ever.
    """
    material = json.dumps(
        {
            "format": FORMAT,
            "model": model,
            "lenses": sorted(lenses),
            "prompts": {name: hashlib.sha256(text.encode()).hexdigest()[:16] for name, text in sorted(prompts.items())},
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


class ResultCache:
    """Findings and notes for chunks already analysed under one recipe."""

    def __init__(self, path: Path, recipe: str) -> None:
        self.path = path
        self.recipe = recipe
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")

    def close(self) -> None:
        self.conn.close()

    def remember(self, chunk_id: str, findings: Iterable[dict[str, Any]], note: str) -> None:
        """Write one chunk's result down. A chunk with nothing found is a result.

        "This unit is clean" is exactly as expensive to establish as a finding
        and exactly as reusable, and storing only the hits would leave every
        clean unit paying full price on every run.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO results (chunk_id, recipe, findings, note) VALUES (?, ?, ?, ?)",
            (chunk_id, self.recipe, json.dumps(list(findings)), note or ""),
        )
        self.conn.commit()

    def warm(self, store: ChunkStore, chunk_ids: Iterable[str]) -> int:
        """Copy what is already known into this run's store. Returns how many.

        Marked inspected, which is what `plan` reads -- so a warmed chunk is
        skipped by the ordinary path rather than by a special case, and lands in
        `chunks_cached` where the summary already reports it.
        """
        wanted = [chunk_id for chunk_id in chunk_ids if not store.is_inspected(chunk_id)]
        if not wanted:
            return 0

        warmed = 0
        for batch in _batched(wanted, 500):
            placeholders = ",".join("?" * len(batch))
            rows = self.conn.execute(
                f"SELECT chunk_id, findings, note FROM results WHERE recipe = ? AND chunk_id IN ({placeholders})",
                (self.recipe, *batch),
            ).fetchall()
            for row in rows:
                try:
                    findings = json.loads(row["findings"])
                except (TypeError, ValueError):
                    continue
                if findings:
                    store.add_findings(row["chunk_id"], findings)
                if row["note"]:
                    store.set_note(row["chunk_id"], row["note"])
                store.mark_inspected(row["chunk_id"])
                warmed += 1
        return warmed


def _batched(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    """SQLite has a limit on how many parameters one statement may bind, and a
    large upload is well past it."""
    for start in range(0, len(items), size):
        yield items[start : start + size]
