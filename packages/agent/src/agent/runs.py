from __future__ import annotations

import hashlib
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
from .files import Tree, Upload, UploadRejected, prepare, read_files, read_zip
from .index import ChunkStore, IndexResult, build_index
from .schema import Report
from .graph.checkpoints import read_history, read_state, write_state
from .trace import SpanStore

__all__ = [
    "MAX_UPLOAD_BYTES",
    "MAX_UPLOAD_FILES",
    "MAX_SINGLE_FILE_BYTES",
    "Run",
    "STATUS_CANCELLED",
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
    "runs_with_same_tree",
    "tree_sha",
    "new_run",
    "run_label",
    "store_zip",
    "write_files",
]

from .files import MAX_SINGLE_FILE_BYTES, MAX_UPLOAD_BYTES, MAX_UPLOAD_FILES  # noqa: E402

STATUS_CREATED = "created"
STATUS_INDEXING = "indexing"
STATUS_INSPECTING = "inspecting"
STATUS_INTERRUPTED = "interrupted"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class Run:
    run_id: str
    config: AgentConfig = field(default_factory=AgentConfig)

    def store(self) -> ChunkStore:
        return ChunkStore(self.run_id, self.config)

    def spans(self) -> SpanStore:
        return SpanStore(self.run_id, self.config)

    def read_file(self, path: str) -> str | None:
        with session_scope(self.config) as session:
            return session.scalar(select(FileRow.content).where(FileRow.run_id == self.run_id, FileRow.path == path))

    def put_file(self, name: str, raw: bytes) -> str:
        upload = prepare(name, raw)
        self.put_files([upload])
        return upload.path

    def put_files(self, uploads: list[Upload]) -> int:
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
        with session_scope(self.config) as session:
            return list(
                session.scalars(select(FileRow.path).where(FileRow.run_id == self.run_id).order_by(FileRow.path))
            )

    def file_contents(self) -> dict[str, str]:
        with session_scope(self.config) as session:
            rows = session.execute(select(FileRow.path, FileRow.content).where(FileRow.run_id == self.run_id)).all()
        return {path: content for path, content in rows}

    def checkpoints(self, full: bool = False) -> list[dict[str, Any]]:
        return read_history(self.config.database_url, self.run_id, full=full)

    def state(self, checkpoint_id: str | None = None) -> dict[str, Any] | None:
        return read_state(self.config.database_url, self.run_id, checkpoint_id)

    def set_state(
        self,
        values: dict[str, Any],
        checkpoint_id: str | None = None,
        as_node: str | None = None,
    ) -> str | None:
        return write_state(self.config.database_url, self.run_id, values, checkpoint_id, as_node)

    def reset_debug(self) -> None:
        spans = self.spans()
        spans.clear()
        spans.close()
        from .graph.checkpoints import clear_thread

        clear_thread(self.config.database_url, self.run_id)

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
            # Reassigned, not mutated: SQLAlchemy tracks JSONB by identity and
            # never writes an in-place update.
            row.meta = merged
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
    if not run_id or not run_id.isalnum():
        return None
    cfg = config or AgentConfig()
    with session_scope(cfg) as session:
        if session.get(RunRow, run_id) is None:
            return None
    return Run(run_id=run_id, config=cfg)


LABEL_FILES = 2


def run_label(run: Run) -> tuple[list[str], int]:
    names = run.files()
    return [PurePath(name).name for name in names[:LABEL_FILES]], len(names)


def describe_run(run: Run) -> dict[str, Any]:
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
        "started": started,
    }


def _has_spans(session: Any, run_id: str) -> bool:
    from .db import Span

    return bool(session.scalar(select(func.count()).select_from(Span).where(Span.run_id == run_id)))


def list_runs(config: AgentConfig | None = None, owner: str | None = None) -> list[dict[str, Any]]:
    cfg = config or AgentConfig()
    with session_scope(cfg) as session:
        query = select(RunRow.id).order_by(RunRow.updated_at.desc())
        if owner:
            query = query.where(RunRow.owner == owner)
        ids = list(session.scalars(query))
    return [describe_run(Run(run_id=run_id, config=cfg)) for run_id in ids]


def tree_sha(run: Run) -> str | None:
    with session_scope(run.config) as session:
        rows = session.execute(
            select(FileRow.path, FileRow.sha).where(FileRow.run_id == run.run_id).order_by(FileRow.path)
        ).all()
    if not rows:
        return None
    material = "\n".join(f"{path}:{sha}" for path, sha in rows)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def runs_with_same_tree(run: Run, owner: str | None = None) -> list[dict[str, Any]]:
    mine = tree_sha(run)
    if mine is None:
        return []

    with session_scope(run.config) as session:
        size = session.scalar(select(func.count()).select_from(FileRow).where(FileRow.run_id == run.run_id))
        candidates = list(
            session.scalars(
                select(FileRow.run_id)
                .join(RunRow, RunRow.id == FileRow.run_id)
                .where(FileRow.run_id != run.run_id, *([RunRow.owner == owner] if owner else []))
                .group_by(FileRow.run_id)
                .having(func.count() == size)
            )
        )

    matched = [run_id for run_id in candidates if tree_sha(Run(run_id=run_id, config=run.config)) == mine]
    rows = [describe_run(Run(run_id=run_id, config=run.config)) for run_id in matched]
    return sorted(rows, key=lambda row: row.get("updated_at") or 0, reverse=True)


def abandon_live_runs(config: AgentConfig | None = None) -> list[str]:
    cfg = config or AgentConfig()
    with session_scope(cfg) as session:
        ids = list(session.scalars(select(RunRow.id).where(RunRow.status.in_((STATUS_INSPECTING, STATUS_INTERRUPTED)))))
    for run_id in ids:
        Run(run_id=run_id, config=cfg).set_status(
            STATUS_FAILED, error="서버가 다시 시작되어 실행이 끊겼습니다", parked=None, progress=None
        )
    return ids


def delete_run(run: Run) -> None:
    with session_scope(run.config) as session:
        row = session.get(RunRow, run.run_id)
        if row is not None:
            session.delete(row)


def store_zip(run: Run, archive: Path) -> Tree:
    tree = read_zip(archive)
    run.put_files(tree.files)
    return tree


def write_files(run: Run, files: dict[str, bytes]) -> Tree:
    tree = read_files(files)
    run.put_files(tree.files)
    return tree


def index_run(run: Run) -> IndexResult:
    run.set_status(STATUS_INDEXING)
    store = run.store()
    try:
        result = build_index(run.file_contents(), store)
    finally:
        store.close()
    run.write_meta(index=result.as_dict())
    return result


def iter_all_files(run: Run) -> Iterator[str]:
    yield from run.files()
