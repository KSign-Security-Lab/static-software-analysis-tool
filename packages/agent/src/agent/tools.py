"""The tool implementations, as plain functions, so they can be tested without a
subprocess in the way. Every filesystem entry point takes the run root and goes
from the run's own files, so a tool cannot reach anything the run does not
hold. That used to be enforced by `agent.paths.resolve_within` against a run
root; the root is gone and the files are rows, so a path that is not a key is
simply not a file.

`run_in_sandbox` was here and is not: it needed a real tree to run a command
against, and nothing materialises one. See the note where it stood."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

from .index.store import ChunkStore

# A tool that dumps a megabyte into the context is worse than one that refuses.
MAX_READ_CHARS = 100_000
MAX_GREP_MATCHES = 200
MAX_LIST_ENTRIES = 1_000


@dataclass(frozen=True)
class ToolError(Exception):
    """A tool refused. Returned to the model as text, not raised at it."""

    message: str

    def __str__(self) -> str:
        return self.message


def read_file(files: Mapping[str, str], path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read one of the run's files. Lines are 1-based and inclusive.

    Takes the run's files as a mapping rather than a root directory. The
    confinement that used to guard this -- `resolve_within`, and the whole of
    `paths.py` -- is gone with the directory: a path that is a dictionary key
    cannot escape anything, and a name that is not a key is simply not a file.
    """
    text = files.get(path)
    if text is None:
        raise ToolError(f"not a file: {path}")

    if start_line is None and end_line is None:
        return text[:MAX_READ_CHARS]

    lines = text.splitlines()
    first = max(1, start_line or 1)
    last = min(len(lines), end_line or len(lines))
    return "\n".join(lines[first - 1 : last])[:MAX_READ_CHARS]


def list_dir(files: Mapping[str, str], path: str = ".") -> list[str]:
    """Immediate children of a directory, directories marked with a slash.

    There are no directories any more, only paths that share a prefix -- so this
    derives the listing from the keys. The output is unchanged, which is what
    matters: it is what the model reads.
    """
    prefix = "" if path in (".", "", "/") else path.rstrip("/") + "/"
    entries: set[str] = set()
    for name in files:
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix) :]
        if not rest:
            continue
        head, _, tail = rest.partition("/")
        entries.add(head + "/" if tail else head)
    if not entries and prefix:
        raise ToolError(f"not a directory: {path}")
    return sorted(entries)[:MAX_LIST_ENTRIES]


def _matches(name: str, pattern: str) -> bool:
    """Glob a run-relative path, with `Path.glob`'s semantics rather than
    `PurePath.match`'s.

    `match` anchors at the *right*, so `*.c` matched `lib/util.c` as happily as
    `main.c` -- while `**/*.c` matched only the nested one. That is backwards
    from the `root.glob(...)` this replaced and from what the prompts describe.
    `full_match` anchors the whole path, which is the old behaviour exactly.
    """
    return PurePosixPath(name).full_match(pattern)


def glob_files(files: Mapping[str, str], pattern: str) -> list[str]:
    """Run-relative paths matching a glob."""
    return sorted(name for name in files if _matches(name, pattern))[:MAX_LIST_ENTRIES]


def grep(files: Mapping[str, str], pattern: str, glob: str | None = None) -> list[str]:
    """Search the run's files for a pattern.

    Always the Python scan now. It used to prefer ripgrep with the run root as
    `cwd`, and there is no root to point a subprocess at -- so what was the
    fallback is the whole implementation. Slower on a large tree; the output
    format is byte-for-byte what `rg --line-number --no-heading` produced,
    because that is what the prompts describe and what the trace renders.
    """
    try:
        compiled = re.compile(pattern)
    except re.error as err:
        raise ToolError(f"invalid pattern: {err}") from err

    results: list[str] = []
    for name in sorted(files):
        if glob and not _matches(name, glob):
            continue
        for number, line in enumerate(files[name].splitlines(), start=1):
            if compiled.search(line):
                results.append(f"{name}:{number}:{line}")
                if len(results) >= MAX_GREP_MATCHES:
                    return results
    return results


# -- graph tools, answered from the index rather than by searching -----------


def _describe(chunk: Any) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "file": chunk.file,
        "symbol": chunk.symbol,
        "kind": chunk.kind,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }


def callers_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    """From the resolved link graph, so exact."""
    out: list[dict[str, Any]] = []
    for definition in store.definition_of(symbol):
        out.extend(_describe(chunk) for chunk in store.callers_of(definition.chunk_id))
    return out


def callees_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    """Chunks a symbol calls."""
    out: list[dict[str, Any]] = []
    for definition in store.definition_of(symbol):
        out.extend(_describe(chunk) for chunk in store.callees_of(definition.chunk_id))
    return out


def definition_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    """Where a symbol is defined, with its source."""
    return [{**_describe(chunk), "body": chunk.body[:MAX_READ_CHARS]} for chunk in store.definition_of(symbol)]


# -- sandboxed execution -----------------------------------------------------


# `run_in_sandbox` lived here.
#
# It ran a command against the run's tree under bubblewrap or docker, and a
# tree is exactly what a run no longer has: the files are rows, and nothing
# materialises them. Removed rather than given a temporary directory, which was
# a deliberate call -- a scratch tree written per invocation is a second source
# of truth with a lifetime, and this is the only tool that wanted one.
#
# `GET /agent/graph` reads the roster from the step definitions, so the tool
# stops being advertised by deleting it here rather than by editing a list.
