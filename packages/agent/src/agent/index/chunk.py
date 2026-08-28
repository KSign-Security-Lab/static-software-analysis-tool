"""Source text -> syntactic chunks, via tree-sitter.

One chunk per function or method, plus one per file for the top-level material
they depend on. Fixed windows cut functions in half. Ids are content-derived, so
re-indexing an unchanged function keeps its cached findings.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

from ..languages import LanguageSpec, spec_for_path

#: A chunk covering the file's top-level material rather than one definition.
FILE_CHUNK_KIND = "file"
FUNCTION_CHUNK_KIND = "function"

_WHITESPACE = re.compile(r"\s+")


def normalize_body(text: str) -> str:
    """Reindenting must not invalidate cached findings; changing a token must."""
    return _WHITESPACE.sub(" ", text).strip()


def chunk_id_for(file: str, symbol: str, body: str) -> str:
    """Stable id for a chunk: same file, symbol and body -> same id."""
    digest = hashlib.sha256(f"{file}\x00{symbol}\x00{normalize_body(body)}".encode())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Chunk:
    """One syntactic unit of source, with the symbols it defines and uses."""

    chunk_id: str
    file: str
    symbol: str
    kind: str
    # 1-based, inclusive.
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    body: str
    language: str
    defines: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    types_used: tuple[str, ...] = ()
    includes: tuple[str, ...] = ()
    # False for file chunks: their body is a synthesized concatenation with
    # definition bodies elided, so offsets in it do not map onto the file.
    body_is_verbatim: bool = True

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def numbered_body(self) -> str:
        """Body with ``NNN| `` prefixes, as fed to the model."""
        return self.numbered_range(self.start_line, self.end_line)

    def numbered_range(self, first: int, last: int) -> str:
        """The same view, restricted to absolute lines ``first``-``last``.

        The numbers are already absolute file lines, so a region's range is
        directly comparable to a ``Span``'s and nothing needs translating.

        The width is computed over the whole body rather than the slice, so one
        unit renders with the same padding wherever it is cut -- otherwise the
        same line arrives as ``42|`` in one prompt and ``042|`` in another, and
        the ``NNN| `` the prompts promise stops being one thing.
        """
        lines = self.body.splitlines() or [""]
        width = max(3, len(str(self.start_line + len(lines) - 1)))
        return "\n".join(
            f"{number:0{width}d}| {line}"
            for number, line in ((self.start_line + i, line) for i, line in enumerate(lines))
            if first <= number <= last
        )


def line_windows(chunk: Chunk, budget: int) -> list[tuple[int, int]]:
    """Consecutive line ranges covering the unit, each rendering within ``budget``.

    Line-aware, which is the whole point. ``truncate`` is a character prefix cut:
    it can slice mid-line, and on a large unit it means whatever reads the body
    never sees the tail at all. Deciding *where in a unit* is worth close reading
    while unable to see the end of it is the same failure this pass exists to
    fix, one level up -- so the unit is read in passes instead.

    Always at least one window, and never an empty one: a line longer than the
    budget still gets a window of its own, because dropping it would be the cut
    this is here to avoid.
    """
    lines = chunk.body.splitlines() or [""]
    rendered = chunk.numbered_range(chunk.start_line, chunk.end_line).splitlines() or [""]
    # Measured on the rendered form, prefixes included: that is what is sent.
    widths = [len(line) + 1 for line in rendered] or [1]

    windows: list[tuple[int, int]] = []
    first = chunk.start_line
    spent = 0
    for offset in range(len(lines)):
        cost = widths[offset] if offset < len(widths) else 1
        number = chunk.start_line + offset
        if spent and spent + cost > budget:
            windows.append((first, number - 1))
            first = number
            spent = 0
        spent += cost
    windows.append((first, chunk.start_line + len(lines) - 1))
    return windows


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Any) -> Iterator[Any]:
    """Every node in the subtree, including the root."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _descendants_excluding_definitions(node: Any, spec: LanguageSpec) -> Iterator[Any]:
    """A nested definition is its own chunk, so its calls are not the outer
    chunk's references."""
    for child in node.children:
        if spec.is_definition(child.type):
            continue
        yield child
        yield from _descendants_excluding_definitions(child, spec)


def definition_name(node: Any, source: bytes) -> str:
    """Most grammars expose a ``name`` field; C and C++ nest a ``declarator``
    chain that has to be walked down to the identifier."""
    named = node.child_by_field_name("name")
    if named is not None:
        return _text(named, source)

    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        if declarator.type in {"identifier", "field_identifier", "type_identifier", "operator_name"}:
            return _text(declarator, source)
        nested = declarator.child_by_field_name("declarator")
        if nested is None:
            for child in declarator.children:
                if child.type in {"identifier", "field_identifier"}:
                    return _text(child, source)
            break
        declarator = nested

    for child in _walk(node):
        if child.type == "identifier":
            return _text(child, source)
    return "<anonymous>"


def _callee_name(call: Any, source: bytes) -> str | None:
    """Rightmost identifier of a qualified callee: ``obj.method()`` -> ``method``.
    Loose on purpose -- the resolver matches bare names, and over-broad is
    cheaper than a missed edge."""
    target = call.child_by_field_name("function") or call.child_by_field_name("constructor")
    if target is None:
        for child in call.children:
            if child.type not in {"argument_list", "(", ")"}:
                target = child
                break
    if target is None:
        return None
    if target.type in {"identifier", "field_identifier", "type_identifier"}:
        return _text(target, source)
    last: str | None = None
    for node in _walk(target):
        if node.type in {"identifier", "field_identifier", "type_identifier"}:
            last = _text(node, source)
    return last


@dataclass
class _Symbols:
    references: list[str] = field(default_factory=list)
    types_used: list[str] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)


def _collect(nodes: Sequence[Any], spec: LanguageSpec, source: bytes) -> _Symbols:
    """Pull references, types, definitions and includes out of a node set."""
    found = _Symbols()
    for node in nodes:
        if node.type in spec.call_nodes:
            callee = _callee_name(node, source)
            if callee:
                found.references.append(callee)
        elif node.type in spec.type_nodes:
            found.types_used.append(_text(node, source))
        elif node.type in spec.type_definition_nodes:
            named = node.child_by_field_name("name")
            if named is not None:
                found.defines.append(_text(named, source))
            else:
                for child in node.children:
                    if child.type == "type_identifier":
                        found.defines.append(_text(child, source))
                        break
        elif node.type in spec.import_nodes:
            found.includes.append(_text(node, source).strip())
    return found


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    """Order-preserving, so chunk rows are stable."""
    seen: dict[str, None] = {}
    for value in values:
        cleaned = value.strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return tuple(seen)


def chunk_source(file: str, text: str) -> list[Chunk]:
    """Chunk one file. Returns [] for files with no grammar we support."""
    spec = spec_for_path(file)
    if spec is None:
        return []

    from tree_sitter_language_pack import get_parser

    source = text.encode("utf-8")
    tree = get_parser(spec.name).parse(source)
    root = tree.root_node

    chunks: list[Chunk] = []
    definitions = [node for node in _walk(root) if spec.is_definition(node.type)]

    for node in definitions:
        symbol = definition_name(node, source)
        body = _text(node, source)
        inner = list(_descendants_excluding_definitions(node, spec))
        found = _collect(inner, spec, source)
        chunks.append(
            Chunk(
                chunk_id=chunk_id_for(file, symbol, body),
                file=file,
                symbol=symbol,
                kind=FUNCTION_CHUNK_KIND,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                body=body,
                language=spec.name,
                defines=(symbol,),
                references=_dedupe(found.references),
                types_used=_dedupe(found.types_used),
            )
        )

    chunks.append(_file_chunk(file, text, source, root, spec, definitions))
    return chunks


def _file_chunk(
    file: str,
    text: str,
    source: bytes,
    root: Any,
    spec: LanguageSpec,
    definitions: Sequence[Any],
) -> Chunk:
    """Top-level material with definition bodies elided.

    A buffer's declared size lives here, not in the function that overflows it.
    """
    definition_ranges = [(node.start_byte, node.end_byte) for node in definitions]
    top_level = [
        node
        for node in root.children
        if not any(start <= node.start_byte and node.end_byte <= end for start, end in definition_ranges)
    ]
    found = _collect([n for node in top_level for n in _walk(node)], spec, source)
    body = "\n".join(_text(node, source) for node in top_level)
    return Chunk(
        chunk_id=chunk_id_for(file, file, body),
        file=file,
        symbol=file,
        kind=FILE_CHUNK_KIND,
        start_line=1,
        end_line=max(1, len(text.splitlines())),
        start_byte=0,
        end_byte=len(source),
        body=body,
        language=spec.name,
        defines=_dedupe(found.defines),
        references=_dedupe(found.references),
        types_used=_dedupe(found.types_used),
        includes=_dedupe(found.includes),
        body_is_verbatim=False,
    )
