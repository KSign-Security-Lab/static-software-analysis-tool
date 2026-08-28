# F2-A Generalization Test — RemoteStart, Part 2: isolating the two failure causes

**Follow-up to** [`f2a-generalization-test-remote-start.md`](./f2a-generalization-test-remote-start.md).

**Goal:** the Part-1 run failed with zero output. Two candidate causes were
hypothesized:

- **A. missing F1 KB coverage** — `RemoteStartTransaction` had no profile, so the
  action was never analyzed.
- **B. missing registrar-call handler discovery** — the handler is registered via
  a runtime `register_handler(id, fn)` call, a shape no discovery strategy models.

This run isolates them: add **only** the minimum legitimate F1 KB profile for
`RemoteStartTransaction` (no implementation changes, no handler names, no
fixture-specific discovery hints, no `process_request` / `register_handler`
special-casing), then rerun the **exact same C code**. The purpose is not to make
the test pass — it is to prove A and B are independent.

**Result:** proven independent. Adding F1 knowledge moved the pipeline from
"action invisible" to "action analyzed, handler undiscoverable." Output is still
empty, but now for a strictly deeper reason (B), with A eliminated.

All findings below come from the real pipeline run + direct CPG probes. ruff and
mypy are clean; the existing 20-test suite still passes.

---

## 1. Exact KB profile added (F1 only — no discovery logic)

```python
# actions:
ActionProfile(
    action_name="RemoteStartTransaction",
    protocol_version="ocpp1.6", component_type="charge_point",
    message_direction="CSMS_TO_CHARGE_POINT",
    sensitive_fields=["idTag"],
    action_symbols=["ACTION_REMOTE_START"],   # no handler_patterns
    numeric_ids=[15],
),

# fields:
FieldProfile(
    action_name="RemoteStartTransaction", field_name="idTag",
    semantic_type="remote_authorization_id", trust_level="remote_ocpp_input",
    dangerous_sink_domain=["COMMAND_EXECUTION"],   # reuses existing sink domain (system/popen/exec*)
    expected_checks=["RS_IDTAG_INPUT_VALIDATION", "RS_NO_SHELL_EXECUTION"],
    related_cwe=["CWE-78", "CWE-20"],
    field_source_aliases=["idTag"],
),

# expected checks:
ExpectedCheckProfile("RS_IDTAG_INPUT_VALIDATION", "INPUT_VALIDATION", CWE-20)
ExpectedCheckProfile("RS_NO_SHELL_EXECUTION", "SAFE_API_USAGE",
    negative_sink_domains=["COMMAND_EXECUTION"], CWE-78)   # reaching a shell sink = negative evidence

# + RootCause remote_id_to_command_injection
```

What was deliberately **not** added: no `handler_patterns`, no `process_request`,
no `register_handler`, no dispatch-shape hints. The `COMMAND_EXECUTION` sink
domain (which already contains `system`) is reused, not modified. No F2-A
implementation code changed.

---

## 2. Is RemoteStart now selected for analysis?

**Yes. Cause A is fixed.**

```
all_actions() -> ['UpdateFirmware', 'DataTransfer', 'SetChargingProfile', 'RemoteStartTransaction']
RemoteStartTransaction selected: True
```

The result now contains a **fourth limitation naming RemoteStartTransaction** —
proof that `analyze()` reached it and *attempted* discovery (previously it was
not even in the loop).

---

## 3. Exact discovery strategies attempted (all four ran, all returned `None`)

```
strategy1 string        : None   # no LITERAL == "RemoteStartTransaction"
strategy2 enum/switch   : None   # JUMP_TARGET count = 0 (for-loop dispatch, no case labels)
strategy3 registration  : None   # METHOD_REF parent is a CALL, not an initializer/assignment
strategy4 name fallback : None   # no handler_patterns; no method name contains "remote_start_transaction"
=> _step1_discover_handler: None
```

---

## 4. Is `register_handler(ACTION_REMOTE_START, process_request)` detected?

**No.** The identifiers are now known (id 15 / `ACTION_REMOTE_START` are in the
KB), but strategy 3 never evaluates them, because it gates on the `METHOD_REF`'s
**parent node type** *before* looking at ids — and the parent here is a plain
function-call node, not an initializer/assignment. The pairing a human reads
trivially is structurally invisible to the current strategy.

---

## 5. Exact CPG nodes & parent relationships

```
JUMP_TARGET count: 0                         # -> strategy 2 has nothing to match

process_request  METHOD_REF  id=124554051584  line=40
   parent: label=CALL  name='register_handler'
           code='register_handler(ACTION_REMOTE_START, process_request)'

register_handler  CALL  id=30064771118  name='register_handler'
   arg[1]: label=CALL        code='ACTION_REMOTE_START'      # the id
   arg[2]: label=METHOD_REF  code='process_request'          # the handler
```

The id and the handler-ref **are** siblings — but as **arguments of a
`register_handler` CALL**. Strategy 3 requires the `METHOD_REF`'s parent to be
`<operator>.arrayInitializer` or `<operator>.assignment`; `register_handler` is
neither, so the node is skipped at the gate.

---

## 6. First stage that fails after KB coverage is fixed

**Stage 1 — Handler Discovery**, specifically the **registrar-call registration
pattern**. It is no longer a KB-selection failure (the action is analyzed); it is
a genuine discovery-strategy gap. Stages 2–9 never run.

---

## 7. Exact final JSON

```json
{
  "handler_maps": [], "field_bindings": [], "flow_candidates": [],
  "sink_mappings": [], "expected_check_matchings": [],
  "missing_check_candidate_sets": [], "evidence_packages": [], "candidate_fragments": [],
  "limitations": [
    "No handler found for action 'UpdateFirmware' in this CPG (dispatch may be dynamic / in another translation unit).",
    "No handler found for action 'DataTransfer' in this CPG (dispatch may be dynamic / in another translation unit).",
    "No handler found for action 'SetChargingProfile' in this CPG (dispatch may be dynamic / in another translation unit).",
    "No handler found for action 'RemoteStartTransaction' in this CPG (dispatch may be dynamic / in another translation unit)."
  ]
}
```

---

## Conclusion — the two limitations are independent, and now proven so

| | Before KB profile | After KB profile |
|---|---|---|
| **A. KB/F1 coverage** | RemoteStart not in `all_actions()`; never analyzed | **Fixed** — analyzed; 4th limitation emitted |
| **B. Registrar-call discovery** | masked by A | **Still fails** — all 4 strategies return `None` despite correct ids, because the `id↔METHOD_REF` pairing lives in a `register_handler(...)` CALL, not an initializer/assignment |

Adding only F1 knowledge advanced the pipeline from "action invisible" to "action
analyzed, handler undiscoverable." That is exactly the isolation intended:
**A was necessary but not sufficient; B is a separate, structural
discovery-strategy gap.** The output is still empty, but for a strictly different
and deeper reason than in Part 1.

The fix for B would be an **implementation** change (teach the registration-table
strategy to also follow the arguments of a registrar-style CALL, i.e. a call
whose args pair an action-id token with a `METHOD_REF` to an internal function).
That change was **not** made here — this run is diagnostic only.

---

## Provenance

- Same C input as Part 1 (`ACTION_REMOTE_START` dispatched via a runtime
  function-pointer registry).
- KB change: `packages/ssat/src/ssat/f2a/kb.py` only (one action, one field, two
  expected checks, one root cause). No implementation change.
- Verified via the real embedded-Joern → `ssat.f2a` run and per-strategy
  instrumentation; ruff + mypy clean; existing test suite (20 tests) green.
