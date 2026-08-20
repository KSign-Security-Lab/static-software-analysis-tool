"""Runs: create, populate, inspect, report.

A run was a directory under ``artifacts/agent-runs/<run_id>/`` holding the
uploaded source, three SQLite databases and three JSON files -- seven artifacts
held together by a path convention, with nothing enforcing that they belonged
to each other and no way to ask anything across runs.

A run is a row now, and everything it owns cascades off it (see ``agent/db/``).
Two things fall out that the directory could not give: deleting one is a single
statement rather than an ``rmtree`` that might half-succeed, and listing them is
a query rather than 86 directory reads.

``Run`` keeps ``RunPaths``' method surface deliberately -- ``store()``,
``spans()``, ``read_meta()``, ``save_report()`` and the rest -- because eight
call sites across the API and the CLI go through it, and a storage change should
not be a rewrite of those.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Iterator

from sqlalchemy import delete, func, select

from .config import AgentConfig
from .db import File as FileRow
from .db import Run as RunRow
from .db import session_scope
from .files import Upload, UploadRejected, prepare, read_zip
from .index import ChunkStore, IndexResult, build_index
from .schema import Report
from .graph.checkpoints import read_history, read_state, write_state
from .trace import SpanStore

__all__ = [
    "MAX_UPLOAD_BYTES",
    "MAX_UPLOAD_FILES",
    "MAX_SINGLE_FILE_BYTES",
    "Run",
    "STATUS_CREATED",
    "STATUS_DONE",
    "STATUS_FAILED",
    "STATUS_INDEXING",
    "STATUS_INSPECTING",
    "STATUS_INTERRUPTED",
    "UploadRejected",
    "abandon_live_runs",
    "delete_run",
    "describe_run",
    "get_run",
    "index_run",
    "iter_all_files",
    "list_runs",
    "new_run",
    "run_label",
    "store_zip",
    "write_files",
]

# Re-exported: several callers import the caps and the rejection from here, and
# they are about uploads rather than about storage. See ``agent/files.py``.
from .files import MAX_SINGLE_FILE_BYTES, MAX_UPLOAD_BYTES, MAX_UPLOAD_FILES  # noqa: E402

STATUS_CREATED = "created"
STATUS_INDEXING = "indexing"
STATUS_INSPECTING = "inspecting"
#: Stopped at a breakpoint, waiting for a person. Not an end state: the run is
#: still holding its tools and can be told to carry on.
STATUS_INTERRUPTED = "interrupted"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class Run:
    """One run, and everything it owns.

    Holds an id and a config rather than a connection: a run outlives any one
    session, and the methods below each take the session they need. The unit of
    work stays the caller's -- ``store()`` and ``spans()`` hand back a handle
    that commits when it is closed, which is what the existing
    ``store = paths.store(); ...; store.close()`` shape already expected.
    """

    run_id: str
    config: AgentConfig = field(default_factory=AgentConfig)

    # -- the stores ---------------------------------------------------------

    def store(self) -> ChunkStore:
        return ChunkStore(self.run_id, self.config)

    def spans(self) -> SpanStore:
        return SpanStore(self.run_id, self.config)

    # -- files --------------------------------------------------------------

    def read_file(self, path: str) -> str | None:
        """One file's text, or None. Replaces reading it off disk."""
        with session_scope(self.config) as session:
            return session.scalar(select(FileRow.content).where(FileRow.run_id == self.run_id, FileRow.path == path))

    def put_file(self, name: str, raw: bytes) -> str:
        """Create or replace one file. Returns the stored path."""
        upload = prepare(name, raw)
        self.put_files([upload])
        return upload.path

    def put_files(self, uploads: list[Upload]) -> int:
        """Write a batch in one transaction.

        One transaction because a half-written upload is worse than a rejected
        one: the indexer would run over a tree the user did not send.
        """
        if not uploads:
            return 0
        with session_scope(self.config) as session:
            existing = {
                row.path: row
                for row in session.scalars(
                    select(FileRow).where(
                        FileRow.run_id == self.run_id,
                        FileRow.path.in_([u.path for u in uploads]),
                    )
                )
            }
            for upload in uploads:
                row = existing.get(upload.path)
                if row is None:
                    session.add(
                        FileRow(
                            run_id=self.run_id,
                            path=upload.path,
                            content=upload.content,
                            size=upload.size,
                            sha=upload.sha,
                        )
                    )
                else:
                    row.content, row.size, row.sha = upload.content, upload.size, upload.sha
        return len(uploads)

    def delete_file(self, path: str) -> bool:
        with session_scope(self.config) as session:
            result = session.execute(delete(FileRow).where(FileRow.run_id == self.run_id, FileRow.path == path))
            return bool(result.rowcount)

    def files(self) -> list[str]:
        """Every uploaded file, indexable or not.

        Not the same list as the index: a tree contains files the chunker skips, and
        a patch built from this run still has to ship them.
        """
        with session_scope(self.config) as session:
            return list(
                session.scalars(select(FileRow.path).where(FileRow.run_id == self.run_id).order_by(FileRow.path))
            )

    def file_contents(self) -> dict[str, str]:
        """The whole tree at once, for the indexer."""
        with session_scope(self.config) as session:
            rows = session.execute(select(FileRow.path, FileRow.content).where(FileRow.run_id == self.run_id)).all()
        return {path: content for path, content in rows}

    # -- checkpoints --------------------------------------------------------

    def checkpoints(self, full: bool = False) -> list[dict[str, Any]]:
        """This run's state at each super-step, oldest first.

        Summarised by default: a history is read far more often than it is
        expanded, and the bulky fields are a second copy of what is already
        stored. ``full`` is for when someone actually looks inside a step.
        """
        return read_history(self.config.database_url, self.run_id, full=full)

    def state(self, checkpoint_id: str | None = None) -> dict[str, Any] | None:
        """One checkpoint's state in full, for reading or editing."""
        return read_state(self.config.database_url, self.run_id, checkpoint_id)

    def set_state(
        self,
        values: dict[str, Any],
        checkpoint_id: str | None = None,
        as_node: str | None = None,
    ) -> str | None:
        """Write state over a checkpoint, branching the run there."""
        return write_state(self.config.database_url, self.run_id, values, checkpoint_id, as_node)

    def reset_debug(self) -> None:
        """Clear the trace and the checkpoints before a *fresh* inspection.

        Two attempts interleaved in one thread read as one incoherent run, and a
        stale checkpoint would make LangGraph resume where the last attempt
        stopped instead of starting over.

        Only ever on a fresh start. Calling this when resuming or branching
        would throw away the history the resume is being measured against --
        including every branch taken off it.
        """
        spans = self.spans()
        spans.clear()
        spans.close()
        from .graph.checkpoints import clear_thread

        clear_thread(self.config.database_url, self.run_id)

    # -- metadata and the report --------------------------------------------

    def _row(self, session: Any) -> RunRow | None:
        return session.get(RunRow, self.run_id)

    def read_meta(self) -> dict[str, Any]:
        with session_scope(self.config) as session:
            row = self._row(session)
            return dict(row.meta or {}) if row else {}

    def write_meta(self, **updates: Any) -> dict[str, Any]:
        with session_scope(self.config) as session:
            row = self._row(session)
            if row is None:
                return {}
            merged = {**(row.meta or {}), **updates}
            # Reassigned rather than mutated: SQLAlchemy tracks JSONB by
            # identity, so an in-place update is not seen and never written.
            row.meta = merged
            # Mirrored onto the columns the run list sorts and filters on. The
            # meta blob stays the free-form record `write_meta(**updates)`
            # always was; these two are the ones queries need.
            if "status" in updates:
                row.status = updates["status"]
            if "error" in updates:
                row.error = updates["error"]
            row.updated_at = time.time()
            return merged

    def set_status(self, status: str, **extra: Any) -> None:
        self.write_meta(status=status, **extra)

    def save_report(self, report: Report) -> None:
        with session_scope(self.config) as session:
            row = self._row(session)
            if row is not None:
                row.report = report.model_dump(mode="json")

    def load_report(self) -> Report | None:
        with session_scope(self.config) as session:
            row = self._row(session)
            payload = row.report if row else None
        return Report.model_validate(payload) if payload else None


def new_run(config: AgentConfig | None = None, owner: str | None = None) -> Run:
    """Create an empty run."""
    cfg = config or AgentConfig()
    run_id = uuid.uuid4().hex[:12]
    with session_scope(cfg) as session:
        session.add(
            RunRow(
                id=run_id,
                owner=owner,
                status=STATUS_CREATED,
                meta={"status": STATUS_CREATED, "run_id": run_id},
            )
        )
    return Run(run_id=run_id, config=cfg)


def get_run(run_id: str, config: AgentConfig | None = None) -> Run | None:
    """Look up an existing run, refusing anything that is not a plain id."""
    if not run_id or not run_id.isalnum():
        return None
    cfg = config or AgentConfig()
    with session_scope(cfg) as session:
        if session.get(RunRow, run_id) is None:
            return None
    return Run(run_id=run_id, config=cfg)


#: How many file names a run is labelled with before the rest become "+3".
LABEL_FILES = 2


def run_label(run: Run) -> tuple[list[str], int]:
    """The first few file names in a run, and how many there are.

    A run id is a random hex string, which tells you nothing about which run it
    was. What people recognise is the code they put in it.
    """
    names = run.files()
    return [PurePath(name).name for name in names[:LABEL_FILES]], len(names)


def describe_run(run: Run) -> dict[str, Any]:
    """One row of the run list: what it was, when, and whether it ran."""
    with session_scope(run.config) as session:
        row = session.get(RunRow, run.run_id)
        if row is None:
            return {"run_id": run.run_id}
        meta = dict(row.meta or {})
        updated = row.updated_at
        started = _has_spans(session, run.run_id)
    names, total = run_label(run)
    return {
        "run_id": run.run_id,
        **meta,
        "owner": row.owner,
        "files": names,
        "file_count": total,
        "updated_at": updated,
        # A span is written the first time an inspection runs, so its presence
        # is the honest answer to "did this ever do anything".
        "started": started,
    }


def _has_spans(session: Any, run_id: str) -> bool:
    from .db import Span

    return bool(session.scalar(select(func.count()).select_from(Span).where(Span.run_id == run_id)))


def list_runs(config: AgentConfig | None = None, owner: str | None = None) -> list[dict[str, Any]]:
    """Every run, most recently touched first.

    Sorted by time rather than by id: an id is a random hex string, so sorting
    on it shuffles the list into an order that means nothing to anybody.

    ``owner`` filters to one typed name. It is not a security boundary -- see
    the API -- it is what stops a shared list being full of runs nobody
    recognises.
    """
    cfg = config or AgentConfig()
    with session_scope(cfg) as session:
        query = select(RunRow.id).order_by(RunRow.updated_at.desc())
        if owner:
            query = query.where(RunRow.owner == owner)
        ids = list(session.scalars(query))
    return [describe_run(Run(run_id=run_id, config=cfg)) for run_id in ids]


def abandon_live_runs(config: AgentConfig | None = None) -> list[str]:
    """Mark every run still claiming to be in flight as failed.

    Called once on startup. A run lives on a worker thread in this process and
    its progress channel is in-process only, so a run recorded as ``inspecting``
    or ``interrupted`` when the server starts is a run whose process is gone --
    there is nothing left to resume it, and nothing that will ever finish it.
    Left alone it reads as "실행 중" for ever, which is the one thing a status
    is for.
    """
    cfg = config or AgentConfig()
    with session_scope(cfg) as session:
        ids = list(session.scalars(select(RunRow.id).where(RunRow.status.in_((STATUS_INSPECTING, STATUS_INTERRUPTED)))))
    for run_id in ids:
        Run(run_id=run_id, config=cfg).set_status(
            STATUS_FAILED, error="서버가 다시 시작되어 실행이 끊겼습니다", parked=None, progress=None
        )
    return ids


def delete_run(run: Run) -> None:
    """Remove a run and everything in it.

    One statement. Every per-run table has a cascading foreign key, so there is
    no order to get right and nothing that can be half-deleted -- which an
    ``rmtree`` over seven artifacts could always be.
    """
    with session_scope(run.config) as session:
        row = session.get(RunRow, run.run_id)
        if row is not None:
            session.delete(row)


def store_zip(run: Run, archive: Path) -> int:
    """Store an uploaded zip. Returns the file count."""
    return run.put_files(read_zip(archive))


def write_files(run: Run, files: dict[str, bytes]) -> int:
    """Store an explicit set of uploaded files, with the same name rules."""
    return run.put_files([prepare(name, content) for name, content in files.items()])


def index_run(run: Run) -> IndexResult:
    """Index a populated run."""
    run.set_status(STATUS_INDEXING)
    store = run.store()
    try:
        result = build_index(run.file_contents(), store)
    finally:
        store.close()
    run.write_meta(index=result.as_dict())
    return result


def iter_all_files(run: Run) -> Iterator[str]:
    """Every uploaded file, indexable or not.

    Not the same list as the index: a tree contains files the chunker skips, and
    a patch built from this run still has to ship them.
    """
    yield from run.files()
