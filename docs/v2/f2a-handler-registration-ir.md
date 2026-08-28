# F2-A Handler Discovery — dispatch-shape survey and the registration IR

**Follow-up to** the RemoteStart generalization tests
([part 1](./f2a-generalization-test-remote-start.md),
[part 2](./f2a-generalization-test-remote-start-part2-kb-isolation.md)).

**Question:** is the fix for registry-style dispatch "add another discovery
strategy," or should handler discovery be re-modeled around a generic
registration fact? To answer empirically, six structurally different dispatch
implementations were run against the **unmodified** pipeline, using an action
already in the KB (`RemoteStartTransaction`) and an **identical handler + flow
body** in every variant — so the only variable is the registration/dispatch
mechanism, isolating handler discovery.

**Answer:** the generic model. The current strategy already generalized
*accidentally* to a shape it wasn't designed for (V4), proving it is really
trying to express one shape-agnostic idea; and the four failing shapes each fail
for a *different* structural reason, so per-shape strategies would be a treadmill.
This document records the survey and the first refactor step: a
`HandlerRegistration` intermediate representation with two AST extractors,
behavior-preserving (20 tests green).

---

## 1. Dispatch-shape survey (current implementation, before refactor)

All six share the same handler (`process_request`) and flow
(`req->idTag → run_authorize → system`). Strategies 1/2/4 never fire (no string
literal, no switch/case, generic handler name), so this measures strategy 3
(registration) alone.

| Variant | Registration syntax | Discovered? | Pkgs | METHOD_REF parent |
|---|---|:--:|:--:|---|
| **V1** | aggregate initializer `{ id, fn }` | **yes** | 1 | `arrayInitializer` |
| **V4** | id-indexed fn-ptr array `h[id] = fn` | **yes** | 1 | `assignment` |
| **V2** | separate assignments `t[i].id=…; t[i].fn=…` | no | 0 | `assignment` |
| **V3** | registrar fn `register_handler(id, fn)` | no | 0 | `CALL:register_handler` |
| **V5** | macro `REGISTER(id, fn)` (assignment-style) | no | 0 | `CALL:REGISTER` |
| **V6** | indirect two-level `register → store` | no | 0 | `CALL:register_handler` |

### The abstraction boundary

Strategy 3 fires **iff the action-id token and the handler `METHOD_REF` co-occur
as siblings inside one `arrayInitializer` or `assignment` AST subtree.** That one
rule explains every outcome:

- **V1 pass** — id and ref are the two elements of one `{ id, fn }` initializer.
- **V4 pass (the key signal)** — `h[ACTION_REMOTE_START] = process_request`: the
  id is the LHS array index, the ref is the RHS, both under **one** assignment.
  It matched **even though the strategy was written for tables, not arrays.** The
  real underlying concept is *local id↔ref co-occurrence* — the code was an
  accidental, partial encoding of it.
- **V2 fail** — parent *is* an assignment (the node-type gate passes), but the id
  is in a **different statement** (`t[i].action = …`) from the ref
  (`t[i].fn = …`); they are correlated only by writing to the same slot `t[i]`.
- **V3 / V6 fail** — the id↔ref pairing is in the **arguments of a CALL**, not an
  initializer/assignment.
- **V5 fail** — the C frontend does **not** expand the function-like macro;
  `REGISTER(...)` stays a `CALL:REGISTER`, so it fails like a registrar call.

### Which CPG relations each shape actually needs

The current strategy uses **AST only**. That is sufficient for V1/V4 but
structurally cannot reach the others:

| Shape | Relation(s) required |
|---|---|
| V1 aggregate init | AST (sibling co-occurrence) |
| V4 single assignment | AST (LHS-index / RHS co-occurrence) |
| V2 correlated field stores | AST (same receiver `t[i]`) + **DFG** (same slot / index value) |
| V3 / V6 registrar call | **Call Graph** (resolve registrar callee) + AST (args) + intra-callee store check; interprocedural |
| V5 macro | preprocessing, or treat unexpanded `CALL:<macro>` like a registrar |

---

## 2. The refactor: a `HandlerRegistration` IR

Rather than one monolithic `_handler_by_registration_table`, discovery now has
three separated concerns:

```
extractors (many, per syntax)  ->  HandlerRegistration[]  ->  one KB-driven consumer
```

**IR (in `pipeline.py`):**

```python
@dataclass
class HandlerRegistration:
    action_id_symbols: Set[str]   # upper-cased id tokens co-located with the ref
    action_id_literals: Set[str]  # numeric/string literal ids co-located with the ref
    callback_method: int          # METHOD node of the handler
    mechanism: str                # AGGREGATE_INIT | INDEXED_ASSIGN | ...
    evidence_node: int            # the initializer/assignment node proving the pairing
    ref_node: int                 # the METHOD_REF node
```

**Consumer** (`_handler_by_registration`) is now shape-agnostic: for the current
action, find a registration whose `action_id_symbols`/`action_id_literals` match
the KB profile's `action_symbols`/`numeric_ids`, and return its
`callback_method`. Matching logic lives here once; it never grows when a new
syntax is added.

**Extractor wired in today** (`_extract_registrations_ast`): a `METHOD_REF` whose
enclosing node is a single `arrayInitializer` (`AGGREGATE_INIT`) or `assignment`
(`INDEXED_ASSIGN`), with the id spelled in the *same* node. This subsumes the
previous strategy exactly — V1 and V4 still pass with identical evidence
(`DISPATCH_HANDLER_TABLE` / `HANDLER_REF`, confidence 0.8).

### Behavior after refactor (unchanged, now with mechanism recorded)

```
variant                      discovered    mechanism        pkgs  IR-regs(mechanisms)
V1_aggregate_initializer     process_request AGGREGATE_INIT     1  AGGREGATE_INIT
V4_id_indexed_fnptr_array    process_request INDEXED_ASSIGN     1  INDEXED_ASSIGN
V2_separate_assignments      (none)          -                  0  INDEXED_ASSIGN   <- reg found, but NO id
V3_registrar_function        (none)          -                  0  (no IR regs)     <- no reg found at all
V5_macro_assignment_style    (none)          -                  0  INDEXED_ASSIGN   <- reg found, but NO id
V6_indirect_two_level        (none)          -                  0  (no IR regs)
```

The IR makes the two remaining gaps *precise*, and shows they are different:

- **V2 / V5** — an `INDEXED_ASSIGN` registration **is** produced (the `.fn = …`
  store is seen), but it carries **no action id**, because the id is in a sibling
  statement. → future **DFG slot-correlation extractor**: correlate the `.fn=`
  store with the `.action=` store by shared receiver/slot, then merge their ids.
- **V3 / V6** — **no** registration is produced at all (the `METHOD_REF` parent is
  a plain `CALL`). → future **Call-Graph registrar extractor**: a call passing an
  `(id-token, internal METHOD_REF)` pair, resolved through the callee that stores
  the fn parameter into a table. Keys on structure, not the name
  `register_handler`.

This is the payoff of the IR: "discovery is weak" becomes "two named extractors
are missing, each needing one additional CPG relation."

---

## 3. Honest limits

- The IR does not *make* the hard shapes easy. V3/V6 still need real
  interprocedural reasoning; V5 needs macro handling the frontend declined to do.
  The IR gives each a clean home and a uniform output — it does not remove the
  analysis cost.
- Some shapes remain fundamentally out of static scope regardless of extractors:
  runtime-computed action ids, ids from config/DB, registration in another
  translation unit. With the IR, those can at least be *reported*
  ("registration mechanism seen, id not statically resolvable") instead of a
  silent empty result.
- Matching is substring-based (`token in symbol`); a future extractor should
  prefer exact-token matching where the CPG gives clean identifiers, to avoid
  incidental matches.

---

## 4. Recommendation (confirmed by the data)

Proceed with the generic registration model, not more one-off strategies. Order:

1. **Done** — `HandlerRegistration` IR + the two AST extractors (this refactor).
2. Next — DFG slot-correlation extractor (unblocks V2, and macro cases that
   expand to separate assignments).
3. Then — Call-Graph registrar extractor (unblocks V3/V6, the real-world OCPP
   registrar idiom).

String/enum/name strategies stay as-is; they are orthogonal dispatch mechanisms,
not registration.

---

## Provenance

- Six variants share one handler/flow body; only registration differs. Action
  `RemoteStartTransaction` (already in the KB) so KB coverage is not the blocker.
- Verified via the real embedded-Joern → `ssat.f2a` run + direct IR inspection.
- Refactor: `packages/ssat/src/ssat/f2a/pipeline.py` only (IR dataclass, extractor,
  consumer; strategy renamed `_handler_by_registration_table` → `_handler_by_registration`).
  No KB change. ruff + mypy clean; existing 20 tests green (behavior preserved).
