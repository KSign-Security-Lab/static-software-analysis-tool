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
    #: Keywords that make a definition invisible outside its own file.
    #:
    #: For `reach`: a unit nothing in the tree calls is only *unreachable* if
    #: nothing outside the tree could call it either. In C that is `static`; in
    #: Java and C# it is `private`. Empty where the grammar has no such keyword,
    #: which is not the same as "everything is visible" -- see `file_local_prefix`.
    file_local_keywords: frozenset[str] = frozenset()
    #: A leading string on the *symbol* that means the same thing by convention.
    #:
    #: Python has no private keyword and a leading underscore is what the
    #: language actually uses; Go decides export by the case of the first letter,
    #: which `file_local_lowercase` covers instead. Empty means neither applies.
    file_local_prefix: str = ""
    #: Whether a lower-case initial means unexported. Go, and only Go.
    file_local_lowercase: bool = False

    def is_definition(self, node_type: str) -> bool:
        return node_type in self.definition_nodes

    def is_file_local(self, symbol: str, declaration: str) -> bool:
        """Whether this definition can be called from outside its own file.

        Given the symbol and the first line or so of its declaration, because
        that is what the index keeps: a real visibility analysis would need a
        second parse, and every rule below is a keyword or a naming convention
        that is decided on that line. Conservative on purpose -- saying "not
        local" costs a finding the weaker label `unreferenced`, and saying
        "local" wrongly would hide one.
        """
        if self.file_local_keywords:
            words = set(declaration.replace("(", " ").split())
            if self.file_local_keywords & words:
                return True
        if self.file_local_prefix and symbol.startswith(self.file_local_prefix):
            # Dunder methods are called by the interpreter, not by name.
            if not symbol.startswith("__"):
                return True
        if self.file_local_lowercase and symbol[:1].islower():
            return True
        return False


_SPECS: tuple[LanguageSpec, ...] = (
    LanguageSpec(
        name="c",
        file_local_keywords=frozenset({"static"}),
        definition_nodes=frozenset({"function_definition"}),
        call_nodes=frozenset({"call_expression"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"preproc_include"}),
        type_definition_nodes=frozenset({"type_definition", "struct_specifier", "enum_specifier", "union_specifier"}),
    ),
    LanguageSpec(
        name="cpp",
        file_local_keywords=frozenset({"static"}),
        definition_nodes=frozenset({"function_definition"}),
        call_nodes=frozenset({"call_expression"}),
        type_nodes=frozenset({"type_identifier", "qualified_identifier"}),
        import_nodes=frozenset({"preproc_include"}),
        type_definition_nodes=frozenset({"type_definition", "struct_specifier", "class_specifier", "enum_specifier"}),
    ),
    LanguageSpec(
        name="java",
        file_local_keywords=frozenset({"private"}),
        definition_nodes=frozenset({"method_declaration", "constructor_declaration"}),
        call_nodes=frozenset({"method_invocation", "object_creation_expression"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"import_declaration"}),
        type_definition_nodes=frozenset({"class_declaration", "interface_declaration", "enum_declaration"}),
    ),
    LanguageSpec(
        name="python",
        file_local_prefix="_",
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
        file_local_keywords=frozenset({"private"}),
        definition_nodes=frozenset({"function_declaration", "method_definition", "generator_function_declaration"}),
        call_nodes=frozenset({"call_expression", "new_expression"}),
        type_nodes=frozenset({"type_identifier"}),
        import_nodes=frozenset({"import_statement"}),
        type_definition_nodes=frozenset({"class_declaration", "interface_declaration", "type_alias_declaration"}),
    ),
    LanguageSpec(
        name="go",
        file_local_lowercase=True,
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
        file_local_keywords=frozenset({"private"}),
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
