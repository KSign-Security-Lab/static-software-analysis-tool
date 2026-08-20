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
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

#: Caps on what an upload may contain, and they defend two different things.
#:
#: The totals are a resource-exhaustion defence: a zip bomb is still a zip bomb
#: when the destination is a table, and a table is *easier* to fill than a disk.
#: Exceeding either is a refusal, because there is no version of the request that
#: makes sense.
MAX_UPLOAD_FILES = 20_000
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
#: The per-file cap is not a defence, it is a judgement about what is worth
#: keeping -- and so it *skips* rather than refuses. A real project carries
#: generated artifacts (a 260 MB `pkix1.json` beside the C it was derived from),
#: and refusing the whole upload over one of them cost the reader every other
#: file for nothing: the indexer skips anything over `MAX_FILE_BYTES` -- 1.5 MB --
#: so a file this size was never going to be inspected either way.
#:
#: Skipped rather than stored, and the difference is visible: `file_contents`
#: loads every row as text, so the indexer, the inspection, the MCP tools and the
#: archive would each pay a quarter of a gigabyte of memory for a file none of
#: them reads. The archive therefore does not contain it, which is why every
#: intake path reports what it passed over instead of doing it quietly.
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024


class UploadRejected(ValueError):
    """The archive was malformed, hostile, or bigger than the totals allow."""


@dataclass(frozen=True)
class Skipped:
    """A file that was not stored, and why."""

    path: str
    size: int
    reason: str = "too_large"


@dataclass(frozen=True)
class Tree:
    """What an upload amounted to: the files kept, and the ones passed over.

    A pair rather than a bare list because the second half has to reach the
    screen. An upload that quietly dropped a file would be a tree the reader did
    not send being inspected as though it were -- which is the objection the old
    outright refusal was answering, and it is answered better by saying so.
    """

    files: list[Upload]
    skipped: list[Skipped] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """For `meta`, and for the intake response the page reads."""
        return {
            "kept": len(self.files),
            "skipped": [{"path": each.path, "size": each.size, "reason": each.reason} for each in self.skipped],
        }


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


def read_zip(archive: Path) -> Tree:
    """Every file in an uploaded zip, validated and capped.

    `ZipFile.extractall` was never used and still is not: it happily writes
    through `../` entries on some Python versions and has no size accounting.
    Each entry is checked individually, and the accounting is on the *declared*
    size so a bomb is refused before it is read.

    An entry over the per-file cap is skipped and reported; the totals are
    refusals. That combination is what keeps the bomb defence intact while a
    generated artifact stops costing the reader the rest of their project: one
    absurd entry is passed over, and a thousand merely-large ones still add up
    past `MAX_UPLOAD_BYTES` and are refused together.
    """
    kept: list[Upload] = []
    skipped: list[Skipped] = []
    total_bytes = 0

    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_UPLOAD_FILES:
                raise UploadRejected(f"archive has {len(infos)} entries; the limit is {MAX_UPLOAD_FILES}")

            for info in infos:
                if info.is_dir():
                    continue
                name = safe_name(info.filename)
                if name is None:
                    raise UploadRejected(f"unsafe path in archive: {info.filename!r}")
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    # Never opened, so its bytes never count against the total.
                    skipped.append(Skipped(path=name, size=info.file_size))
                    continue

                total_bytes += info.file_size
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise UploadRejected(f"archive expands past {MAX_UPLOAD_BYTES} bytes")

                with zf.open(info) as src:
                    kept.append(prepare(info.filename, src.read()))
    except zipfile.BadZipFile as err:
        raise UploadRejected(f"not a readable zip archive: {err}") from err

    return Tree(files=kept, skipped=skipped)


def read_files(payload: dict[str, bytes]) -> Tree:
    """The same rules for a set of loose files.

    The multipart path had no caps at all -- only `read_zip` counted anything --
    so a folder upload could put whatever it liked into the table while the same
    tree zipped up was refused. The asymmetry was invisible and the wrong way
    round: the folder picker is the path most people use.
    """
    kept: list[Upload] = []
    skipped: list[Skipped] = []
    total_bytes = 0

    if len(payload) > MAX_UPLOAD_FILES:
        raise UploadRejected(f"upload has {len(payload)} files; the limit is {MAX_UPLOAD_FILES}")

    for name, raw in payload.items():
        stored = safe_name(name)
        if len(raw) > MAX_SINGLE_FILE_BYTES:
            skipped.append(Skipped(path=stored or name, size=len(raw)))
            continue
        total_bytes += len(raw)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise UploadRejected(f"upload is larger than {MAX_UPLOAD_BYTES} bytes")
        kept.append(prepare(name, raw))

    return Tree(files=kept, skipped=skipped)
