from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

from .index.store import ChunkStore

MAX_READ_CHARS = 100_000
MAX_GREP_MATCHES = 200
MAX_LIST_ENTRIES = 1_000


@dataclass(frozen=True)
class ToolError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def read_file(files: Mapping[str, str], path: str, start_line: int | None = None, end_line: int | None = None) -> str:
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
    return PurePosixPath(name).full_match(pattern)


def glob_files(files: Mapping[str, str], pattern: str) -> list[str]:
    return sorted(name for name in files if _matches(name, pattern))[:MAX_LIST_ENTRIES]


def grep(files: Mapping[str, str], pattern: str, glob: str | None = None) -> list[str]:
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
    out: list[dict[str, Any]] = []
    for definition in store.definition_of(symbol):
        out.extend(_describe(chunk) for chunk in store.callers_of(definition.chunk_id))
    return out


def callees_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for definition in store.definition_of(symbol):
        out.extend(_describe(chunk) for chunk in store.callees_of(definition.chunk_id))
    return out


def definition_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    return [{**_describe(chunk), "body": chunk.body[:MAX_READ_CHARS]} for chunk in store.definition_of(symbol)]
