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
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .config import AgentConfig
from .db import CachedResult, session_factory
from .index.store import ChunkStore

log = logging.getLogger(__name__)

#: Bumped when what is stored changes shape. An old row under a new format is
#: not a hit, which is cheaper than migrating something entirely rebuildable.
FORMAT = "1"

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
    """Findings and notes for chunks already analysed under one recipe.

    The one table with no ``run_id``. A chunk id is derived from the code, so an
    unchanged unit in a *new* run hits what an older run concluded -- and tying
    this to a run would defeat the only thing it exists for.
    """

    def __init__(self, recipe: str, config: AgentConfig | None = None) -> None:
        self.recipe = recipe
        self._sessions = session_factory(config)

    def close(self) -> None:
        """Nothing to close: sessions are per-operation. Kept for the callers
        that pair it with the constructor."""

    def remember(self, chunk_id: str, findings: Iterable[dict[str, Any]], note: str) -> None:
        """Write one chunk's result down. A chunk with nothing found is a result.

        "This unit is clean" is exactly as expensive to establish as a finding
        and exactly as reusable, and storing only the hits would leave every
        clean unit paying full price on every run.
        """
        payload = json.dumps(list(findings))
        with self._sessions() as session:
            statement = insert(CachedResult).values(
                chunk_id=chunk_id, recipe=self.recipe, findings=payload, note=note or ""
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["chunk_id", "recipe"],
                    set_={"findings": payload, "note": note or ""},
                )
            )
            session.commit()

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
        # One statement. The batching that used to be here worked around
        # SQLite's bound-parameter ceiling; `IN` over an array has no such
        # limit, so the loop and its helper are gone.
        with self._sessions() as session:
            rows = session.execute(
                select(CachedResult.chunk_id, CachedResult.findings, CachedResult.note).where(
                    CachedResult.recipe == self.recipe, CachedResult.chunk_id.in_(wanted)
                )
            ).all()

        for chunk_id, raw, note in rows:
            try:
                findings = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if findings:
                store.add_findings(chunk_id, findings)
            if note:
                store.set_note(chunk_id, note)
            store.mark_inspected(chunk_id)
            warmed += 1
        return warmed


