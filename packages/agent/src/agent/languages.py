"""Per-language tree-sitter node names, in one table.

Every language names the same concepts differently -- a call is
``call_expression`` in C, ``method_invocation`` in Java, ``call`` in Python. The
indexer needs those names in four places, so they live here once instead of as
branches scattered through the walker.

Adding a language means adding a :class:`LanguageSpec` and an extension entry;
no indexer code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

#: Grammar names come from ``tree_sitter_language_pack.get_parser``.


@dataclass(frozen=True)
class LanguageSpec:
    """Which node types mean what, for one grammar."""

    name: str
    #: Node types that become a chunk of their own.
    definition_nodes: frozenset[str]
    #: Node types whose callee identifier is an outgoing reference.
    call_nodes: frozenset[str]
    #: Node types that name a type the chunk depends on.
    type_nodes: frozenset[str]
    #: Node types that pull in another file.
    import_nodes: frozenset[str]
    #: Node types that define a type at file scope.
    type_definition_nodes: frozenset[str] = frozenset()

    def is_definition(self, node_type: str) -> bool:
        return node_type in self.definition_nodes


_SPECS: tuple[LanguageSpec, ...] = (
    LanguageSpec(
        name="c",
        definition_nodes=frozenset({"function_definition"}),
        call_nodes=frozenset({"call_expression"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"preproc_include"}),
        type_definition_nodes=frozenset({"type_definition", "struct_specifier", "enum_specifier", "union_specifier"}),
    ),
    LanguageSpec(
        name="cpp",
        definition_nodes=frozenset({"function_definition"}),
        call_nodes=frozenset({"call_expression"}),
        type_nodes=frozenset({"type_identifier", "qualified_identifier"}),
        import_nodes=frozenset({"preproc_include"}),
        type_definition_nodes=frozenset({"type_definition", "struct_specifier", "class_specifier", "enum_specifier"}),
    ),
    LanguageSpec(
        name="java",
        definition_nodes=frozenset({"method_declaration", "constructor_declaration"}),
        call_nodes=frozenset({"method_invocation", "object_creation_expression"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"import_declaration"}),
        type_definition_nodes=frozenset({"class_declaration", "interface_declaration", "enum_declaration"}),
    ),
    LanguageSpec(
        name="python",
        definition_nodes=frozenset({"function_definition"}),
        call_nodes=frozenset({"call"}),
        type_nodes=frozenset(),
        import_nodes=frozenset({"import_statement", "import_from_statement"}),
        type_definition_nodes=frozenset({"class_definition"}),
    ),
    LanguageSpec(
        name="javascript",
        definition_nodes=frozenset({"function_declaration", "method_definition", "generator_function_declaration"}),
        call_nodes=frozenset({"call_expression", "new_expression"}),
        type_nodes=frozenset(),
        import_nodes=frozenset({"import_statement"}),
        type_definition_nodes=frozenset({"class_declaration"}),
    ),
    LanguageSpec(
        name="typescript",
        definition_nodes=frozenset({"function_declaration", "method_definition", "generator_function_declaration"}),
        call_nodes=frozenset({"call_expression", "new_expression"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"import_statement"}),
        type_definition_nodes=frozenset({"class_declaration", "interface_declaration", "type_alias_declaration"}),
    ),
    LanguageSpec(
        name="go",
        definition_nodes=frozenset({"function_declaration", "method_declaration"}),
        call_nodes=frozenset({"call_expression"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"import_declaration"}),
        type_definition_nodes=frozenset({"type_declaration"}),
    ),
    LanguageSpec(
        name="rust",
        definition_nodes=frozenset({"function_item"}),
        call_nodes=frozenset({"call_expression", "macro_invocation"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"use_declaration"}),
        type_definition_nodes=frozenset({"struct_item", "enum_item", "trait_item", "impl_item"}),
    ),
    LanguageSpec(
        name="csharp",
        definition_nodes=frozenset({"method_declaration", "constructor_declaration"}),
        call_nodes=frozenset({"invocation_expression", "object_creation_expression"}),
        type_nodes=frozenset({"identifier"}),
        import_nodes=frozenset({"using_directive"}),
        type_definition_nodes=frozenset({"class_declaration", "interface_declaration", "struct_declaration"}),
    ),
)

SPECS: dict[str, LanguageSpec] = {spec.name: spec for spec in _SPECS}

#: File extension -> grammar name. Only extensions we have a spec for; anything
#: else is not indexed, which is deliberate -- a chunk we cannot parse is a
#: chunk we cannot locate findings in.
EXTENSIONS: dict[str, str] = {
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".hh": "cpp",
    ".java": "java",
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
}


def spec_for_path(path: str) -> LanguageSpec | None:
    """The spec for a file, by extension, or None if we do not index it.

    ``.h`` maps to the C grammar even in C++ projects. The C grammar parses the
    overwhelming majority of headers well enough to find declarations, and
    guessing wrong costs less than skipping the file entirely.
    """
    language = EXTENSIONS.get(PurePosixPath(path.lower()).suffix)
    return SPECS[language] if language else None
