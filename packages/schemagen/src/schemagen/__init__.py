"""Render JSON Schema as TypeScript interfaces.

Hand-writing the TypeScript view of a wire model creates a second definition
that drifts the first time a field is added -- silently, because a missing
optional field in TS is not a type error. This renders it instead, so the
schema is defined once and a test can assert the checked-in file still matches.

Takes ``(name, json_schema)`` pairs, not pydantic models: ``agent`` and ``ssat``
both need it and neither may import the other, so the one thing they can share
is a package that knows about neither.
"""

from .render import UnsupportedSchema, render, schemas_of

__all__ = ["UnsupportedSchema", "render", "schemas_of"]
