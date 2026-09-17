from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from .index import SKIP_DIRS
from .languages import spec_for_path

MAX_UPLOAD_FILES = 20_000
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024


class UploadRejected(ValueError):
    pass


NOISE_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


def is_source(path: str) -> bool:
    return spec_for_path(path) is not None


def is_noise(path: str) -> bool:
    pure = PurePosixPath(path)
    if any(part in SKIP_DIRS for part in pure.parts):
        return True
    return pure.name in NOISE_FILES or pure.name.startswith("._")


SkipReason = Literal["too_large", "binary"]


@dataclass(frozen=True)
class Skipped:
    path: str
    size: int
    reason: SkipReason = "too_large"


@dataclass(frozen=True)
class Tree:
    files: list[Upload]
    skipped: list[Skipped] = field(default_factory=list)
    seen: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "kept": len(self.files),
            "seen": self.seen,
            "skipped": [{"path": each.path, "size": each.size, "reason": each.reason} for each in self.skipped],
        }


@dataclass(frozen=True)
class Upload:
    path: str
    content: str
    size: int
    sha: str


def safe_name(name: str) -> str | None:
    if not name or name.endswith("/"):
        return None
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        return None
    if "\\" in name or (len(name) > 1 and name[1] == ":"):
        return None
    return str(pure)


BINARY_SNIFF_BYTES = 8192


def is_binary(raw: bytes) -> bool:
    return b"\x00" in raw[:BINARY_SNIFF_BYTES]


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").replace("\x00", "\ufffd")


def prepare(name: str, raw: bytes) -> Upload:
    path = safe_name(name)
    if path is None:
        raise UploadRejected(f"unsafe path: {name!r}")
    return Upload(path=path, content=_decode(raw), size=len(raw), sha=hashlib.sha256(raw).hexdigest())


def too_big(what: str) -> str:
    limit = MAX_UPLOAD_BYTES // (1024 * 1024)
    return (
        f"{what}이 {limit}MB를 넘습니다. `.git`, `node_modules`, `build` 같은 디렉터리는 이미 빼고 센 "
        f"값입니다 — 검사할 하위 폴더만 골라 다시 올려 주십시오."
    )


def read_zip(archive: Path) -> Tree:
    kept: list[Upload] = []
    skipped: list[Skipped] = []
    seen = 0

    try:
        with zipfile.ZipFile(archive) as zf:
            total_bytes = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = safe_name(info.filename)
                if name is None:
                    raise UploadRejected(f"unsafe path in archive: {info.filename!r}")
                if is_noise(name):
                    continue
                seen += 1
                if not is_source(name):
                    continue
                if len(kept) >= MAX_UPLOAD_FILES:
                    raise UploadRejected(f"소스 파일이 {MAX_UPLOAD_FILES}개를 넘습니다")
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    skipped.append(Skipped(path=name, size=info.file_size))
                    continue

                total_bytes += info.file_size
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise UploadRejected(too_big("압축 파일"))

                with zf.open(info) as src:
                    raw = src.read()
                if is_binary(raw):
                    skipped.append(Skipped(path=name, size=len(raw), reason="binary"))
                    continue
                kept.append(prepare(info.filename, raw))
    except zipfile.BadZipFile as err:
        raise UploadRejected(f"not a readable zip archive: {err}") from err

    return Tree(files=kept, skipped=skipped, seen=seen)


def read_files(payload: dict[str, bytes]) -> Tree:
    kept: list[Upload] = []
    skipped: list[Skipped] = []
    seen = 0
    total_bytes = 0

    for name, raw in payload.items():
        stored = safe_name(name) or name
        if is_noise(stored):
            continue
        seen += 1
        if not is_source(stored):
            continue
        if len(kept) >= MAX_UPLOAD_FILES:
            raise UploadRejected(f"소스 파일이 {MAX_UPLOAD_FILES}개를 넘습니다")
        if len(raw) > MAX_SINGLE_FILE_BYTES:
            skipped.append(Skipped(path=stored, size=len(raw)))
            continue
        total_bytes += len(raw)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise UploadRejected(too_big("올린 파일"))
        if is_binary(raw):
            skipped.append(Skipped(path=stored, size=len(raw), reason="binary"))
            continue
        kept.append(prepare(name, raw))

    return Tree(files=kept, skipped=skipped, seen=seen)
