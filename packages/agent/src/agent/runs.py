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
from .index import ChunkStore, IndexResult, build_index, iter_source_files
from .schema import Finding, FindingDiff, Report
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
    def report_path(self) -> Path:
        return self.base / "report.json"

    @property
    def meta_path(self) -> Path:
        return self.base / "meta.json"

    def store(self) -> ChunkStore:
        return ChunkStore(self.index_db)

    def spans(self) -> SpanStore:
        return SpanStore(self.trace_db)

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


def list_runs(config: AgentConfig | None = None) -> list[dict[str, Any]]:
    root = runs_root(config)
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), reverse=True):
        if child.is_dir():
            out.append({"run_id": child.name, **RunPaths(child.name, child).read_meta()})
    return out


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


def file_tree(paths: RunPaths) -> list[str]:
    """Run-relative paths of every indexable file, for the editor's file list."""
    root = paths.source
    return [str(PurePosixPath(*p.relative_to(root).parts)) for p in iter_source_files(root)]


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
