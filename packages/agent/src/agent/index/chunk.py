"""Source text -> syntactic chunks, via tree-sitter.

Fixed-window chunking is wrong for code: it cuts functions in half and destroys
the only unit an analyser can reason about. A chunk here is a *syntactic* unit --
one per function or method definition, plus one per file holding the top-level
material (includes, macros, globals, type definitions) that the functions depend
on.

Chunk ids are content-derived, so re-indexing an unchanged function yields the
same id and its cached findings survive.
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
    """Collapse whitespace runs, for content hashing.

    Reindenting a function should not invalidate its cached findings, but
    changing a token must. Whitespace collapsing is the line between the two.
    """
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
    #: 1-based, inclusive, matching how editors and compilers count.
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
    #: True when ``body`` is exactly ``source[start_byte:end_byte]``. File chunks
    #: set this False: their body is a synthesized concatenation of the
    #: top-level nodes with definition bodies elided, so offsets within it do
    #: not map onto the file. Anything resolving a location must read the file
    #: rather than index into ``body`` -- see :mod:`agent.locate`.
    body_is_verbatim: bool = True

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def numbered_body(self) -> str:
        """The body with ``NNN| `` line prefixes, as fed to the model.

        The model needs line numbers to talk about locations, but it must not
        copy the prefix into ``anchor_text``; the prompt says so and
        :mod:`agent.locate` strips it defensively anyway.
        """
        lines = self.body.splitlines() or [""]
        width = max(3, len(str(self.start_line + len(lines) - 1)))
        return "\n".join(f"{self.start_line + i:0{width}d}| {line}" for i, line in enumerate(lines))


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
    """Walk a subtree but do not descend into nested definitions.

    A nested function is its own chunk; counting its calls as the outer chunk's
    references would make the link graph claim edges that do not exist.
    """
    for child in node.children:
        if spec.is_definition(child.type):
            continue
        yield child
        yield from _descendants_excluding_definitions(child, spec)


def definition_name(node: Any, source: bytes) -> str:
    """The declared name of a definition node.

    Most grammars expose a ``name`` field. C and C++ do not -- they nest a
    ``declarator`` chain that has to be walked down to the identifier, and the
    same walk handles pointer returns (``char *f(void)``) and function pointers.
    """
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
    """The identifier being called, for a call-shaped node.

    Only the *rightmost* identifier is taken from a qualified callee, so
    ``obj.method()`` resolves as ``method`` and ``a::b::c()`` as ``c``. That is
    deliberately loose: the resolver matches on bare symbol names, and a
    slightly over-broad candidate set is cheaper than missing the edge.
    """
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
    """Order-preserving dedupe -- order is stable, so chunk rows are stable."""
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
    """The file's top-level material, with definition bodies elided.

    Struct layouts, typedefs, globals and includes are what a function's
    vulnerability usually turns on -- a buffer's declared size lives here, not in
    the function that overflows it. Keeping them as their own chunk means every
    function can be given its file's context without re-reading the whole file.
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
