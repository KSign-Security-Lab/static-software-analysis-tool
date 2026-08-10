"""Run workspaces: create, populate, inspect, report.

A run is a directory under ``artifacts/agent-runs/<run_id>/`` holding the
uploaded source, the chunk index, and the report. Everything the inspection
needs is in there, which is what lets a run be resumed, re-read, or thrown away
as a unit.

Upload extraction is the security boundary. The input is an arbitrary archive
from a browser, so it is treated as hostile: entries that escape the root, are
symlinks, or blow past the size and count caps are rejected rather than
sanitised. A zip bomb and a path traversal look identical to a careless
extractor.
"""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from .config import AgentConfig
from .index import ChunkStore, IndexResult, build_index
from .knowledge import GRAPH_FILE
from .schema import Finding, FindingDiff, Report
from .graph.checkpoints import read_history, read_state, write_state
from .trace import SpanStore

#: Caps on what an upload may contain. A zip that exceeds any of them is
#: rejected outright -- silently truncating an upload would mean inspecting a
#: tree the user did not send.
MAX_UPLOAD_FILES = 20_000
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024

STATUS_CREATED = "created"
STATUS_INDEXING = "indexing"
STATUS_INSPECTING = "inspecting"
#: Stopped at a breakpoint, waiting for a person. Not an end state: the run is
#: still holding its tools and can be told to carry on.
STATUS_INTERRUPTED = "interrupted"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


class UploadRejected(ValueError):
    """The archive was malformed or hostile."""


@dataclass(frozen=True)
class RunPaths:
    """Where one run's artifacts live."""

    run_id: str
    base: Path

    @property
    def source(self) -> Path:
        """The extracted tree. Every filesystem tool is confined to this."""
        return self.base / "src"

    @property
    def index_db(self) -> Path:
        return self.base / "index.db"

    @property
    def trace_db(self) -> Path:
        """Spans, kept apart from the index so re-inspecting cannot disturb the
        record of what happened last time until it is deliberately cleared."""
        return self.base / "trace.db"

    @property
    def checkpoint_db(self) -> Path:
        """LangGraph's state snapshots. One thread, this run."""
        return self.base / "checkpoints.db"

    @property
    def knowledge_graph(self) -> Path:
        """The tree as a graph: what the verify step's tools traverse.

        Beside the index because it is derived from it and is invalidated by
        exactly the same events.
        """
        return self.base / GRAPH_FILE

    @property
    def report_path(self) -> Path:
        return self.base / "report.json"

    @property
    def meta_path(self) -> Path:
        return self.base / "meta.json"

    def store(self) -> ChunkStore:
        return ChunkStore(self.index_db)

    def spans(self) -> SpanStore:
        return SpanStore(self.trace_db)

    def checkpoints(self, full: bool = False) -> list[dict[str, Any]]:
        """This run's state at each super-step, oldest first.

        Summarised by default: a history is read far more often than it is
        expanded, and the bulky fields are a second copy of what is already on
        disk. ``full`` is for when someone actually looks inside a step.
        """
        return read_history(self.checkpoint_db, self.run_id, full=full)

    def state(self, checkpoint_id: str | None = None) -> dict[str, Any] | None:
        """One checkpoint's state in full, for reading or editing."""
        return read_state(self.checkpoint_db, self.run_id, checkpoint_id)

    def set_state(
        self,
        values: dict[str, Any],
        checkpoint_id: str | None = None,
        as_node: str | None = None,
    ) -> str | None:
        """Write state over a checkpoint, branching the run there."""
        return write_state(self.checkpoint_db, self.run_id, values, checkpoint_id, as_node)

    def reset_debug(self) -> None:
        """Clear the trace and the checkpoints before a *fresh* inspection.

        Two attempts interleaved in one thread read as one incoherent run, and
        a stale checkpoint would make LangGraph resume where the last attempt
        stopped instead of starting over.

        Only ever on a fresh start. Calling this when resuming or branching
        would throw away the history the resume is being measured against --
        including every branch taken off it.
        """
        spans = self.spans()
        spans.clear()
        spans.close()
        self.checkpoint_db.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            self.checkpoint_db.with_name(self.checkpoint_db.name + suffix).unlink(missing_ok=True)

    def read_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {}
        loaded: dict[str, Any] = json.loads(self.meta_path.read_text(encoding="utf-8"))
        return loaded

    def write_meta(self, **updates: Any) -> dict[str, Any]:
        meta = self.read_meta()
        meta.update(updates)
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def set_status(self, status: str, **extra: Any) -> None:
        self.write_meta(status=status, **extra)

    def save_report(self, report: Report) -> None:
        self.report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def load_report(self) -> Report | None:
        if not self.report_path.exists():
            return None
        return Report.model_validate_json(self.report_path.read_text(encoding="utf-8"))


def runs_root(config: AgentConfig | None = None) -> Path:
    return (config or AgentConfig()).runs_dir


def new_run(config: AgentConfig | None = None) -> RunPaths:
    """Create an empty run workspace."""
    root = runs_root(config)
    run_id = uuid.uuid4().hex[:12]
    paths = RunPaths(run_id=run_id, base=root / run_id)
    paths.source.mkdir(parents=True, exist_ok=True)
    paths.set_status(STATUS_CREATED, run_id=run_id)
    return paths


def get_run(run_id: str, config: AgentConfig | None = None) -> RunPaths | None:
    """Look up an existing run, refusing anything that is not a plain id."""
    if not run_id or not run_id.isalnum():
        return None
    base = runs_root(config) / run_id
    return RunPaths(run_id=run_id, base=base) if base.is_dir() else None


#: How many file names a run is labelled with before the rest become "+3".
LABEL_FILES = 2


def run_label(paths: RunPaths) -> tuple[list[str], int]:
    """The first few file names in a run, and how many there are.

    A run id is a random hex string, which tells you nothing about which run it
    was. What people recognise is the code they put in it.
    """
    names: list[str] = []
    total = 0
    root = paths.source
    if not root.is_dir():
        return names, total
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            total += 1
            if len(names) < LABEL_FILES:
                names.append(path.name)
    return names, total


def describe_run(paths: RunPaths) -> dict[str, Any]:
    """One row of the run list: what it was, when, and whether it ran.

    Enough to pick a run out of a list without opening it. ``started`` is the
    distinction that matters most: a workspace that was created and never
    inspected has no trace to read and is almost always leftover scaffolding.
    """
    meta = paths.read_meta()
    names, total = run_label(paths)
    try:
        updated = paths.meta_path.stat().st_mtime if paths.meta_path.exists() else paths.base.stat().st_mtime
    except OSError:
        updated = 0.0

    return {
        "run_id": paths.run_id,
        **meta,
        "files": names,
        "file_count": total,
        "updated_at": updated,
        # A trace file is written the first time an inspection runs, so its
        # presence is the honest answer to "did this ever do anything".
        "started": paths.trace_db.exists(),
    }


def list_runs(config: AgentConfig | None = None) -> list[dict[str, Any]]:
    """Every run, most recently touched first.

    Sorted by time rather than by id: an id is a random hex string, so sorting
    on it shuffles the list into an order that means nothing to anybody.
    """
    root = runs_root(config)
    if not root.is_dir():
        return []

    out = [describe_run(RunPaths(child.name, child)) for child in root.iterdir() if child.is_dir()]
    out.sort(key=lambda run: run["updated_at"], reverse=True)
    return out


def abandon_live_runs(config: AgentConfig | None = None) -> list[str]:
    """Mark every run still claiming to be in flight as failed.

    Called once on startup. A run lives on a worker thread in this process and
    its progress channel is in-process only, so a run recorded as ``inspecting``
    or ``interrupted`` when the server starts is a run whose process is gone --
    there is nothing left to resume it, and nothing that will ever finish it.
    Left alone it reads as "실행 중" for ever, which is the one thing a status
    is for.
    """
    abandoned: list[str] = []
    root = runs_root(config)
    if not root.is_dir():
        return abandoned

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        paths = RunPaths(child.name, child)
        if paths.read_meta().get("status") not in (STATUS_INSPECTING, STATUS_INTERRUPTED):
            continue
        paths.set_status(STATUS_FAILED, error="서버가 다시 시작되어 실행이 끊겼습니다", parked=None, progress=None)
        abandoned.append(child.name)

    return abandoned


def delete_run(paths: RunPaths) -> None:
    """Remove a run and everything in it.

    Trying things out leaves workspaces behind, and a list full of them is
    worse than useless. Confined to the run's own directory.
    """
    shutil.rmtree(paths.base, ignore_errors=True)


def _safe_member(name: str) -> PurePosixPath | None:
    """The destination for a zip entry, or None if it must not be extracted."""
    if not name or name.endswith("/"):
        return None
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        return None
    # Windows-style absolute paths and drive letters slip past PurePosixPath.
    if "\\" in name or (len(name) > 1 and name[1] == ":"):
        return None
    return pure


def extract_zip(archive: Path, destination: Path) -> int:
    """Extract an uploaded zip into ``destination``. Returns the file count.

    ``ZipFile.extractall`` is not used: it happily writes through ``../``
    entries on some Python versions and has no size accounting. Each entry is
    checked and written individually instead.
    """
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()
    written = 0
    total_bytes = 0

    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_UPLOAD_FILES:
                raise UploadRejected(f"archive has {len(infos)} entries; the limit is {MAX_UPLOAD_FILES}")

            for info in infos:
                if info.is_dir():
                    continue
                relative = _safe_member(info.filename)
                if relative is None:
                    raise UploadRejected(f"unsafe path in archive: {info.filename!r}")
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    raise UploadRejected(f"{info.filename} is {info.file_size} bytes; too large")

                total_bytes += info.file_size
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise UploadRejected(f"archive expands past {MAX_UPLOAD_BYTES} bytes")

                target = (resolved_destination / relative).resolve()
                if resolved_destination not in target.parents:
                    raise UploadRejected(f"unsafe path in archive: {info.filename!r}")

                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 64)
                written += 1
    except zipfile.BadZipFile as err:
        raise UploadRejected(f"not a readable zip archive: {err}") from err

    return written


def write_files(destination: Path, files: dict[str, bytes]) -> int:
    """Write an explicit set of uploaded files, with the same path rules."""
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()
    written = 0
    for name, content in files.items():
        relative = _safe_member(name)
        if relative is None:
            raise UploadRejected(f"unsafe path: {name!r}")
        target = (resolved_destination / relative).resolve()
        if resolved_destination not in target.parents:
            raise UploadRejected(f"unsafe path: {name!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written += 1
    return written


def index_run(paths: RunPaths) -> IndexResult:
    """Index a populated run workspace."""
    paths.set_status(STATUS_INDEXING)
    store = paths.store()
    try:
        result = build_index(paths.source, store)
    finally:
        store.close()
    paths.write_meta(index=result.as_dict())
    return result


def iter_all_files(paths: RunPaths) -> Iterator[str]:
    """Every uploaded file, indexable or not -- the editor can still show them."""
    root = paths.source
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            yield str(PurePosixPath(*path.relative_to(root).parts))


def diff_reports(before: Report, after: Report) -> FindingDiff:
    """Compare two reports by finding id.

    This is the payoff for content-derived ids: a finding that moved because a
    line was inserted above it is *unchanged*, not simultaneously new and fixed.
    """
    old: dict[str, Finding] = {f.id: f for f in before.findings}
    new: dict[str, Finding] = {f.id: f for f in after.findings}
    return FindingDiff(
        new=[f for finding_key, f in new.items() if finding_key not in old],
        fixed=[f for finding_key, f in old.items() if finding_key not in new],
        unchanged=[f for finding_key, f in new.items() if finding_key in old],
    )
