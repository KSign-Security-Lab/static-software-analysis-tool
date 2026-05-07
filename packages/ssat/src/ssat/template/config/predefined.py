"""Predefined identifier types and mappings."""

PredefinedIdentifierTypes: dict[str, str] = {
    "stdin": "FILE*",
    "stdout": "FILE*",
    "stderr": "FILE*",
    "errno": "int",
    "EOF": "int",
    "NULL": "void*",
    "FILENAME_MAX": "int",
}

IdentifierToLiteralMap: list[str] = ["NULL"]


