"""Base types and enums for template nodes."""

from .base_types import (
    IBaseNode,
    TemplateNodeTypes,
    is_declaration,
    is_expression,
    is_statement,
    is_node_type,
)

__all__ = [
    "TemplateNodeTypes",
    "IBaseNode",
    "is_node_type",
    "is_statement",
    "is_expression",
    "is_declaration",
]


