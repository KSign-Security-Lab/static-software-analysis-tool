# schemagen

JSON Schema → TypeScript interfaces, so a wire type is defined once.

Hand-writing the TypeScript view of a pydantic model creates a second
definition that drifts the first time a field is added — silently, because a
missing optional field in TS is not a type error. Generating it means a test can
assert the checked-in file still matches.

Takes `(name, json_schema)` pairs rather than pydantic models. That is the whole
reason this is its own package: `agent` and `ssat` both need it, neither may
import the other, and the one thing they can share is a package that knows about
neither. It has no dependencies.

Only the subset of JSON Schema the wire models use is handled. Anything else
raises rather than emitting `any` — an `any` here is exactly the drift the
package exists to prevent.

`all_present` renders every property as required, for a schema the server only
ever writes. A pydantic field with a default is absent from `required`, so it
would otherwise render optional — correct for a request body, wrong for a
response always serialised in full, and the difference is `?? []` at every call
site downstream.

It is all-or-nothing rather than per-field because a `default_factory` leaves no
trace in the JSON schema: pydantic cannot emit a default it would have to call.
What is left is the implication — a field with no default *is* required — so
under the flag "not required" can only mean "has a default".
