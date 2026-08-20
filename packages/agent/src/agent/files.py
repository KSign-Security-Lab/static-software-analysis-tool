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
from typing import Literal

from .index import SKIP_DIRS
from .languages import spec_for_path

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
#: Binary files are skipped for a different reason and reported the same way.
#: They cannot be stored at all -- `files.content` is a Postgres text column and
#: Postgres rejects NUL, which is how an AppleDouble fork out of a Mac-made zip
#: took the whole upload down with a 500 -- and storing them mangled, which is
#: what `errors="replace"` used to do, was worse than useless: the archive route
#: writes rows back out as text, so a PNG went in and came out corrupted. A tree
#: of text is a tree this can be honest about.
#:
#: Skipped rather than stored, and the difference is visible: `file_contents`
#: loads every row as text, so the indexer, the inspection, the MCP tools and the
#: archive would each pay a quarter of a gigabyte of memory for a file none of
#: them reads. The archive therefore does not contain it, which is why every
#: intake path reports what it passed over instead of doing it quietly.
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024


class UploadRejected(ValueError):
    """The archive was malformed, hostile, or bigger than the totals allow."""


#: Files that are never anybody's source, only ever litter beside it.
NOISE_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


def is_source(path: str) -> bool:
    """Whether the analyser can read this file at all.

    `spec_for_path` is the authority -- the same table the chunker consults -- so
    this cannot drift from what actually gets inspected. C, C++, Java, Python,
    JS/TS, Go, Rust, C#; anything else has no grammar and produces no chunks.

    Storing the rest was the root of two separate problems. It is most of the
    bytes of a real project, which is how an upload got refused for exceeding a
    cap on files nobody would ever read; and it is where the binaries are, which
    is how an AppleDouble fork took the whole request down with a Postgres error
    about NUL. A tree of files the analyser understands is a tree this can be
    honest about.
    """
    return spec_for_path(path) is not None


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
    pure = PurePosixPath(path)
    if any(part in SKIP_DIRS for part in pure.parts):
        return True
    # Per-file litter, for the same reason and with the same silence. `._*` is an
    # AppleDouble fork, which a Mac writes beside every file it zips.
    return pure.name in NOISE_FILES or pure.name.startswith("._")


#: Why a file was read but not kept.
SkipReason = Literal["too_large", "binary"]


@dataclass(frozen=True)
class Skipped:
    """A file that was not stored, and why."""

    path: str
    size: int
    reason: SkipReason = "too_large"


@dataclass(frozen=True)
class Tree:
    """What an upload amounted to: what was kept, what was passed over, and how
    much there was.

    More than a bare list because the rest has to reach the screen. An upload that
    quietly dropped a file would be a tree the reader did not send being inspected
    as though it were -- which is the objection the old outright refusal was
    answering, and it is answered better by saying so.

    Two kinds of passing over, deliberately told apart. `seen` against `kept` is
    the ordinary shape of a project -- four hundred files, sixty of them source --
    and listing the other three hundred and forty would bury the thing worth
    reading. `skipped` is the surprising kind: a file the analyser *would* have
    read if it could, which is a fact about that file rather than about the tree.
    """

    files: list[Upload]
    skipped: list[Skipped] = field(default_factory=list)
    #: Every file the upload contained, litter aside -- source or not.
    seen: int = 0

    def as_dict(self) -> dict[str, object]:
        """For `meta`, and for the intake response the page reads."""
        return {
            "kept": len(self.files),
            "seen": self.seen,
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


#: How much of a file decides whether it is binary.
#:
#: The same heuristic git uses, and for the same reason: a NUL in the first block
#: is what separates a text file from everything else, and reading further to be
#: certain costs more than being wrong occasionally.
BINARY_SNIFF_BYTES = 8192


def is_binary(raw: bytes) -> bool:
    """Whether these bytes are not text.

    A NUL byte. Cheap, and the consequences of storing one anyway are severe
    enough to be worth a heuristic: `files.content` is a Postgres text column and
    Postgres rejects NUL outright, so an AppleDouble fork out of a Mac-made zip
    (`__MACOSX/._app.c`, whose header is literally `\x00\x05\x16\x07`) failed the
    whole upload with a 500 from inside the ORM flush.
    """
    return b"\x00" in raw[:BINARY_SNIFF_BYTES]


def _decode(raw: bytes) -> str:
    """Text, or a lossy rendering of it.

    `errors="replace"` handles bytes that are not valid UTF-8. It does *not*
    handle NUL, which is perfectly valid UTF-8 and which Postgres will not store
    -- so it is dropped separately here.

    Defence in depth rather than the actual fix: `is_binary` is what keeps such
    files out, and this is what stops a survivor taking the request down with it.
    A stray NUL in an otherwise textual file is not worth refusing an upload over.
    """
    return raw.decode("utf-8", errors="replace").replace("\x00", "\ufffd")


def prepare(name: str, raw: bytes) -> Upload:
    """Validate a name and hash its content."""
    path = safe_name(name)
    if path is None:
        raise UploadRejected(f"unsafe path: {name!r}")
    return Upload(path=path, content=_decode(raw), size=len(raw), sha=hashlib.sha256(raw).hexdigest())


def too_big(what: str) -> str:
    """A refusal somebody can act on.

    Public because `vcs` says the same thing about a clone, and two wordings for
    one limit is how a reader learns the limit twice.

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
                # Before the size and byte checks, and that ordering is the fix:
                # a 260 MB generated `.json` is not a file the reader has to be
                # told about, it is simply not source, and counting it toward the
                # total is what refused whole projects over bytes nobody reads.
                if not is_source(name):
                    continue
                if len(kept) >= MAX_UPLOAD_FILES:
                    raise UploadRejected(f"소스 파일이 {MAX_UPLOAD_FILES}개를 넘습니다")
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    # Never opened, so its bytes never count against the total.
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
    """The same rules for a set of loose files.

    The multipart path had no caps at all -- only `read_zip` counted anything --
    so a folder upload could put whatever it liked into the table while the same
    tree zipped up was refused. The asymmetry was invisible and the wrong way
    round: the folder picker is the path most people use.
    """
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
