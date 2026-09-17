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
FORMAT = "3"

def recipe_of(
    *,
    model: str,
    lenses: Sequence[str],
    prompts: Mapping[str, str],
    reasoning_effort: str = "",
    max_tokens: int = 0,
) -> str:
    material = json.dumps(
        {
            "format": FORMAT,
            "model": model,
            "lenses": sorted(lenses),
            "prompts": {name: hashlib.sha256(text.encode()).hexdigest()[:16] for name, text in sorted(prompts.items())},
            "reasoning_effort": reasoning_effort,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


class ResultCache:
    def __init__(self, recipe: str, config: AgentConfig | None = None) -> None:
        self.recipe = recipe
        self._sessions = session_factory(config)

    def close(self) -> None:
        pass

    def remember(self, chunk_id: str, findings: Iterable[dict[str, Any]], note: str) -> None:
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
        wanted = [chunk_id for chunk_id in chunk_ids if not store.is_inspected(chunk_id)]
        if not wanted:
            return 0

        warmed = 0
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
