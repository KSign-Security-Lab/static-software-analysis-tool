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

from .index import SKIP_DIRS

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


def is_noise(path: str) -> bool:
    """Whether a stored path is something no part of this ever reads.

    The same `SKIP_DIRS` the indexer walks past, applied at intake instead of
    after it. Only the git path did this, so a project *zipped up* stored its
    entire `.git` history, its `node_modules` and its build output as rows -- and
    then the indexer skipped every one of them. Half a gigabyte of a real upload
    is routinely this, which is how a project could exceed `MAX_UPLOAD_BYTES` on
    bytes that were never going to be looked at.

    Excluding them here rather than raising the cap is the honest fix: the tree
    that gets stored is then the tree that gets analysed, and the budget is spent
    on files that matter. Nothing wants `.git` in a patch archive either.
    """
    return any(part in SKIP_DIRS for part in PurePosixPath(path).parts)


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


def _too_big(what: str) -> str:
    """A refusal somebody can act on.

    `archive expands past 524288000 bytes` says what happened and nothing about
    what to do, and the answer is rarely obvious: `.git` and build output are
    already excluded, so what is left is genuinely this large and the reader has
    to choose a subtree.
    """
    limit = MAX_UPLOAD_BYTES // (1024 * 1024)
    return (
        f"{what}이 {limit}MB를 넘습니다. `.git`, `node_modules`, `build` 같은 디렉터리는 이미 빼고 센 "
        f"값입니다 — 검사할 하위 폴더만 골라 다시 올려 주십시오."
    )


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
                if is_noise(name):
                    # Not reported: unlike an oversized source file, nobody is
                    # surprised that `.git` was left out, and listing ten
                    # thousand of them would bury the skips that matter.
                    continue
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    # Never opened, so its bytes never count against the total.
                    skipped.append(Skipped(path=name, size=info.file_size))
                    continue

                total_bytes += info.file_size
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise UploadRejected(_too_big("압축 파일"))

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
        if stored is not None and is_noise(stored):
            continue
        if len(raw) > MAX_SINGLE_FILE_BYTES:
            skipped.append(Skipped(path=stored or name, size=len(raw)))
            continue
        total_bytes += len(raw)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise UploadRejected(_too_big("올린 파일"))
        kept.append(prepare(name, raw))

    return Tree(files=kept, skipped=skipped)
