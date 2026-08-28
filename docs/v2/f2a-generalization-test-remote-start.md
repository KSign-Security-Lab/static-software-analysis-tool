# F2-A Generalization Test — RemoteStart (function-pointer registry dispatch)

**Test intent:** verify F2-A generalizes rather than passing only fixture-specific
patterns. Analyze an intentionally novel input **without** modifying the
implementation, the KB, or adding fixture-specific logic.

**Result up front:** F2-A produced **zero output** on this code. That is the
truthful outcome, not a pass. The pipeline stopped at **Stage 1 (Handler
Discovery)** for all three KB actions. Everything downstream was never reached.

The analysis below is built entirely from the **real** pipeline run (embedded
Joern → `ssat.f2a`, the same `/analyze` path the web uses) plus direct CPG
probes — no hand-derived answers.

---

## Code under test

OCPP `ACTION_REMOTE_START` (=15) dispatched through a **runtime-populated
function-pointer registry**:

```c
#define ACTION_REMOTE_START 15
static Registration g_registry[8];               // uninitialized table

static void register_handler(int action, HandlerFn fn) {   // registrar
    for (int i = 0; i < 8; i++)
        if (g_registry[i].fn == NULL) { g_registry[i].action = action;
                                        g_registry[i].fn = fn; return; }
}
static int execute_authorization(const char *command) { return system(command); }
static const char *extract_id(const RemoteStartRequest *req) {  // getter
    if (req == NULL) return NULL;
    return req->idTag;
}
static char *build_command(const char *id) {                    // builder
    static char buffer[256];
    snprintf(buffer, sizeof(buffer), "authorize --id '%s'", id);
    return buffer;
}
static int perform_remote_start(const char *command) {          // wrapper
    return execute_authorization(command);
}
static int process_request(void *payload) {                     // the handler
    RemoteStartRequest *req = (RemoteStartRequest *)payload;
    if (req == NULL) return -1;
    if (req->connectorId == 0) {                                // guarded check
        if (strlen(req->idTag) >= MAX_ID_LEN) return -1;
    }
    return perform_remote_start(build_command(extract_id(req)));
}
static int dispatch(const OcppFrame *frame) {                   // for-loop dispatch
    for (int i = 0; i < 8; i++) {
        if (g_registry[i].action != frame->action) continue;
        return g_registry[i].fn(frame->payload);               // pointerCall
    }
    return -1;
}
static void initialize(void) {
    register_handler(ACTION_REMOTE_START, process_request);     // registration
}
```

---

## STEP 1 — Predictions (before execution)

| # | Stage | Prediction | Conf. | Reason |
|---|---|---|---|---|
| 1 | Handler Discovery | **FAIL** | 95% | Action is `ACTION_REMOTE_START` (=15) = a RemoteStart transaction. KB knows only `UpdateFirmware`/`DataTransfer`/`SetChargingProfile`. `analyze()` only searches for actions it has an F1 profile for, so it never looks for `process_request`. |
| 2 | Source Binding | **FAIL (not reached)** | 95% | Gated on a handler existing. |
| 3 | Interprocedural DFG | not reached | — | — |
| 4 | Return-value propagation | not reached | — | — |
| 5 | Wrapper propagation | not reached | — | — |
| 6 | Sink detection | not reached | — | `system` *is* a KB sink, but the flow never starts. |
| 7 | Expected-check matching | not reached | — | — |
| 8 | CFG dominance | not reached | — | — |
| 9 | Evidence generation | **FAIL → empty** | 95% | No candidates → empty result + limitations. |

**Secondary prediction (the deeper test):** *even if RemoteStart were in the KB*,
discovery would still fail here, because registration is done through a runtime
`register_handler(id, fn)` **function call**, not a `{id, fn}` initializer — a
mechanism the current registration-table strategy does not model.

---

## STEP 2 — Real execution result

```
handler_maps:      0
field_bindings:    0
evidence_packages: 0
limitations:
  - No handler found for action 'UpdateFirmware' ...
  - No handler found for action 'DataTransfer' ...
  - No handler found for action 'SetChargingProfile' ...
```

Prediction confirmed. **First (and only) stage that executed: Handler Discovery.
It failed for all three KB actions.** Everything downstream was never reached.

---

## STEP 3 — Stage-by-stage (what actually happened)

### Stage 1 — Handler Discovery (the one that ran)

**INPUT:** the CPG + one KB action at a time (`UpdateFirmware`, then
`DataTransfer`, then `SetChargingProfile`).

**PROCESS:** `_step1_discover_handler` runs a 4-strategy cascade per action. For
each KB action here, all four returned `None`. CPG evidence for *why*, from
probing the graph:

- **Strategy 1 (string dispatch)** — searches for a `LITERAL` whose unquoted
  value equals the action name. The only string literals in the CPG are
  `"authorize --id '%s'"` and `"ABC123"`. No `"UpdateFirmware"/"DataTransfer"/
  "SetChargingProfile"`. → fail. *(AST used: LITERAL node values.)*
- **Strategy 2 (enum/switch)** — searches `JUMP_TARGET` (case labels).
  **`JUMP_TARGET` count = 0** — `dispatch()` is a `for`-loop with an `if`, not a
  `switch`. Nothing to match. → fail. *(CFG/AST used: JUMP_TARGET labels — none
  exist.)*
- **Strategy 3 (registration table)** — searches `METHOD_REF` nodes whose AST
  parent is an `<operator>.arrayInitializer` or `<operator>.assignment`, then
  matches a sibling id token. Probe shows the one relevant `METHOD_REF
  process_request` has **AST parent = `CALL register_handler(ACTION_REMOTE_START,
  process_request)`** — a plain function call, not an initializer/assignment.
  The strategy skips it. And even if it inspected those args, the id is
  `ACTION_REMOTE_START` / `15`, which matches **no** KB action's `action_symbols`
  or `numeric_ids` (SetChargingProfile's are `MSG_SET_PROFILE`/
  `ACTION_SET_CHARGING_PROFILE`/`41`). → fail. *(AST used: METHOD_REF + its
  parent/siblings.)*
- **Strategy 4 (name fallback)** — internal method whose name matches a KB
  action's `handler_patterns` or contains its UPPER_SNAKE token. Method names
  present: `register_handler, execute_authorization, extract_id, build_command,
  perform_remote_start, process_request, dispatch, initialize, main`. None
  contain `update_firmware`/`data_transfer`/`set_charging_profile`. → fail.
  *(AST used: METHOD names.)*

**OUTPUT:** `None` × 3 actions → 3 limitation strings.

**EVIDENCE:** `JUMP_TARGET=0`; string literals = `["authorize --id '%s'",
"ABC123"]`; `METHOD_REF process_request` parent = `register_handler(...)` CALL;
register_handler args = `arg1=ACTION_REMOTE_START (CALL)`, `arg2=process_request
(METHOD_REF)`.

**LIMITATIONS:** discovery is **KB-catalog-driven** — it can only find handlers
for actions that already have an F1 profile.

### Stages 2–9

Not executed. In `analyze()`, `_step1_discover_handler` returning `None`
triggers `continue` before source binding — so binding, DFG, return/wrapper
propagation, sink detection, check matching, dominance, and evidence assembly
never run. Reporting them as anything other than "not reached" would be
fabrication.

**Note on the CPG itself:** it was built fully and correctly — Joern computed
AST, CFG, DOMINATE, REACHING_DEF, and a call graph (it even logged the expected
*"Unable to link dynamic CALL … `g_registry[i].fn(...)`"* for the
function-pointer dispatch). The CPG is fine; F2-A just had no F1 profile to point
it at.

---

## STEP 4 — Source→sink chain

**F2-A recovered NONE of this** (it never got past discovery). For completeness,
here is the actual vulnerable chain in the code, which F2-A *would* need to
recover:

```
RemoteStart.idTag                      (untrusted protocol field — NOT in KB)
  ↓  AST: req->idTag  (indirectFieldAccess, leaf "idTag") inside extract_id
  ↓  DFG + return-bridge: extract_id returns it
extract_id(req)  → return value
  ↓  Call Graph: passed as arg to build_command(id)
build_command(id)
  ↓  AST/DFG: snprintf(buffer,"authorize --id '%s'", id)   (string_build)
  ↓  return-bridge: build_command returns static buffer
  ↓  Call Graph: passed to perform_remote_start(command)   [wrapper #1]
perform_remote_start(command)
  ↓  Call Graph: passed to execute_authorization(command)  [wrapper #2]
execute_authorization(command)
  ↓  argument to  system(command)          ← SINK: COMMAND_EXECUTION (CWE-78)
```

Structurally this is almost identical to the `SetChargingProfile`
table/getter/wrapper case that *does* work — getter (`extract_id`), builder
(`build_command`), two wrappers, a guarded check. The return-bridge, arg→param
bridge, and `system`→`COMMAND_EXECUTION` sink mapping are all generic and would
very likely carry this flow **if a candidate had been created.** It wasn't, so
this chain is a manual reading, not F2-A output.

---

## STEP 5 — Check analysis

**F2-A evaluated no checks** (no candidate). The relevant check in the code:

```c
if (req->connectorId == 0) {
    if (strlen(req->idTag) >= MAX_ID_LEN) return -1;
}
```

Had a candidate existed, this is what the *current* logic would conclude:

- **Searched?** Yes — in methods on the taint path.
- **Found?** Yes — `strlen(...) >= MAX_ID_LEN` classifies as `LENGTH_BOUND_CHECK`
  (operator `>=`).
- **Dominates the sink?** **No** — nested under `if (connectorId == 0)`;
  `dominates(cs, departure)=False` → downgraded to **PARTIAL** (the dominance
  logic added earlier).
- **Validates the correct value?** It bounds `idTag`'s *length* — but the sink is
  **command injection**, not overflow. A length cap does **not** neutralize shell
  metacharacters.
- **Verdict:** **NOT SATISFIED** for a command-injection requirement (and only
  PARTIAL even as a length bound). But note: RemoteStart has **no expected-check
  list in the KB**, so there is nothing to match against anyway.

---

## STEP 6 — Final JSON (exact, real)

```json
{
  "source_cpg": "<cpg graphson omitted>",
  "handler_maps": [],
  "field_bindings": [],
  "flow_candidates": [],
  "sink_mappings": [],
  "expected_check_matchings": [],
  "missing_check_candidate_sets": [],
  "evidence_packages": [],
  "candidate_fragments": [],
  "limitations": [
    "No handler found for action 'UpdateFirmware' in this CPG (dispatch may be dynamic / in another translation unit).",
    "No handler found for action 'DataTransfer' in this CPG (dispatch may be dynamic / in another translation unit).",
    "No handler found for action 'SetChargingProfile' in this CPG (dispatch may be dynamic / in another translation unit)."
  ]
}
```

---

## STEP 7 — Self-review of the current implementation

- **Weakest stage: Handler Discovery** — and more fundamentally, the fact that
  discovery is **gated on the KB action catalog**. An OCPP action with no F1
  profile is invisible, regardless of how clean its dataflow is. That's this
  test's outcome.
- **Code pattern most likely to fail: registration via a helper function.**
  `register_handler(id, fn)` splits the `id↔handler` pairing across a call
  boundary — the id/method-ref are arguments to a registration *function*, and
  the actual table write (`g_registry[i].fn = fn`) uses a **parameter**, not a
  `METHOD_REF`. The registration-table strategy only handles inline `{id, fn}`
  initializers / direct assignments, so it can't connect them.
- **CPG relation still incomplete: the call graph for indirect calls.**
  `g_registry[i].fn(payload)` is an `<operator>.pointerCall` Joern leaves
  unlinked ("Unable to link dynamic CALL"). Even with a handler, tracing
  *through* the dynamic dispatch site would need the same table reasoning.
- **Weakest propagation rule:** the return→caller bridge is purely structural
  ("value is a returned expression → propagate to every caller's assignment
  target"). With many callers it can over-propagate (context-insensitive).
- **Remaining false negatives:** (a) any action absent from the KB — like this
  one; (b) handler registered through a wrapper/registrar function; (c)
  sanitizers that aren't a recognized check shape.
- **Remaining false positives:** context-insensitive return/arg bridges can join
  unrelated caller paths; a present-but-irrelevant check (e.g. a length bound
  where the real need is shell-escaping) can read as PARTIALLY_SATISFIED and
  understate risk.

---

## Honest verdict

> *Would this implementation still work on an unrelated real-world codebase, or
> did this example accidentally fit the current implementation?*

**On this specific code, F2-A did not work — it returned nothing — and that's the
truthful result, not a pass.** Two distinct reasons, in order:

1. **First failure (the one that actually happened): RemoteStart isn't in the
   KB.** F2-A is F1-knowledge-driven by design; it only hunts for actions it has
   a profile for. This is a *coverage* limitation, not a discovery-algorithm bug
   — but from a "does it generalize to a new action out of the box" standpoint,
   the answer is **no**: a new action requires a KB entry first.

2. **Even with that entry, it would still fail here** — because the handler is
   registered through a `register_handler()` call, which none of the four
   discovery strategies model. So this example did **not** accidentally fit the
   implementation; it deliberately steps outside it, and exposes a real
   generalization boundary.

Being straight about what generalizes: the *middle* of the pipeline —
return/arg/wrapper propagation, sink mapping, and CFG-dominance check grading —
is genuinely generic and is not fixture-specific (the `SetChargingProfile`
table/getter/wrapper case exercises all of it). The **brittle** parts are the two
ends: (1) discovery is only as broad as the KB's action catalog and its handful
of dispatch-shape strategies, and (2) it has no model for indirect/
registrar-mediated dispatch. A real-world codebase that uses a dispatch shape
outside those strategies, or an action not yet profiled, will get an empty result
— exactly as it did here.
