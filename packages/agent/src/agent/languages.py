from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class LanguageSpec:
    name: str
    definition_nodes: frozenset[str]
    call_nodes: frozenset[str]
    type_nodes: frozenset[str]
    import_nodes: frozenset[str]
    type_definition_nodes: frozenset[str] = frozenset()
    file_local_keywords: frozenset[str] = frozenset()
    file_local_prefix: str = ""
    file_local_lowercase: bool = False

    def is_definition(self, node_type: str) -> bool:
        return node_type in self.definition_nodes

    def is_file_local(self, symbol: str, declaration: str) -> bool:
        if self.file_local_keywords:
            words = set(declaration.replace("(", " ").split())
            if self.file_local_keywords & words:
                return True
        if self.file_local_prefix and symbol.startswith(self.file_local_prefix):
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
    language = EXTENSIONS.get(PurePosixPath(path.lower()).suffix)
    return SPECS[language] if language else None
