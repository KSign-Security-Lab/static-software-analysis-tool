"""The uploaded tree, as rows.

A run's source used to be a directory, and `paths.py` existed to stop a hostile
archive escaping it. A path that is a column cannot escape anything, so the
confinement is gone and what remains is name validation: an entry may not be
absolute, may not contain `..`, and may not be a Windows drive path. Those rules
are still worth enforcing, because a stored path is what the editor, the indexer
and every lookup tool address a file by.

The caps stay too. A 500 MB zip is still a 500 MB zip when the destination is a
table, and a table is *easier* to fill than a disk.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

#: Caps on what an upload may contain. A zip that exceeds any of them is
#: rejected outright -- silently truncating an upload would mean inspecting a
#: tree the user did not send.
MAX_UPLOAD_FILES = 20_000
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024


class UploadRejected(ValueError):
    """The archive was malformed or hostile."""


@dataclass(frozen=True)
class Upload:
    """One file on its way into the database."""

    path: str
    content: str
    size: int
    sha: str


def safe_name(name: str) -> str | None:
    """The stored path for an entry, or None if it must not be stored.

    Was `_safe_member` returning a `PurePosixPath` to join onto a root. There is
    no root to join onto now, so it returns the normalised string that becomes
    `files.path`.
    """
    if not name or name.endswith("/"):
        return None
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        return None
    # Windows-style absolute paths and drive letters slip past PurePosixPath.
    if "\\" in name or (len(name) > 1 and name[1] == ":"):
        return None
    return str(pure)


def _decode(raw: bytes) -> str:
    """Text, or a lossy rendering of it.

    Uploads are arbitrary and some of them are binary. Refusing to store a file
    the reader can see in their own editor would be worse than storing a
    mangled one -- the indexer skips what it cannot parse either way.
    """
    return raw.decode("utf-8", errors="replace")


def prepare(name: str, raw: bytes) -> Upload:
    """Validate a name and hash its content."""
    path = safe_name(name)
    if path is None:
        raise UploadRejected(f"unsafe path: {name!r}")
    return Upload(path=path, content=_decode(raw), size=len(raw), sha=hashlib.sha256(raw).hexdigest())


def read_zip(archive: Path) -> list[Upload]:
    """Every file in an uploaded zip, validated and capped.

    `ZipFile.extractall` was never used and still is not: it happily writes
    through `../` entries on some Python versions and has no size accounting.
    Each entry is checked individually, and the accounting is on the *declared*
    size so a bomb is refused before it is read.
    """
    out: list[Upload] = []
    total_bytes = 0

    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_UPLOAD_FILES:
                raise UploadRejected(f"archive has {len(infos)} entries; the limit is {MAX_UPLOAD_FILES}")

            for info in infos:
                if info.is_dir():
                    continue
                if safe_name(info.filename) is None:
                    raise UploadRejected(f"unsafe path in archive: {info.filename!r}")
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    raise UploadRejected(f"{info.filename} is {info.file_size} bytes; too large")

                total_bytes += info.file_size
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise UploadRejected(f"archive expands past {MAX_UPLOAD_BYTES} bytes")

                with zf.open(info) as src:
                    out.append(prepare(info.filename, src.read()))
    except zipfile.BadZipFile as err:
        raise UploadRejected(f"not a readable zip archive: {err}") from err

    return out
