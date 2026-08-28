# F2-A Phase 3 — evidence-producer design (correlated field store + registrar call)

**Status: IMPLEMENTED.** Producer 1 (correlated field store, commit `a75b9fb`) and
Producer 2 (registrar call, this commit) are shipped with the boundaries below and
the reviewed defaults (registrar depth 2 via `CalculusConfig.registrar_depth`;
behavioral registrar qualification; no partial evidence — a missed store reports
`REGISTRAR_STORE_NOT_REACHED`; Producer 2 reuses Producer 1's slot pairing). Phase 3
adds two evidence producers; it does **not** change the evidence calculus
(`select_corroborate`) or the output model.
Both producers emit `ResolutionEvidence` into the existing dedup → group →
aggregate → select pipeline and never select a handler themselves.

Design decision confirmed by the probes below: implement the **correlated
field-store** producer first (narrower, AST-based); the **registrar-call**
producer reuses it and follows only *resolved call targets*.

The two failing dispatch shapes these close (from the earlier survey):
`V2 separate assignments`, `V5 macro→assignment` (producer 1); `V3 registrar`,
`V6 indirect two-level` (producer 2).

---

## Probe findings (real CPG, not assumed)

### Probe 1 — correlated field stores (`t[0]`, `t[i]`, `e->`)

For every slot form, the `.action` write and the `.fn` write share an **identical
receiver-subtree code**:

```
[init_const] t[0].action = 41   LHS receiver='t[0]'   RHS LITERAL 41
[init_const] t[0].fn = h1       LHS receiver='t[0]'   RHS METHOD_REF h1
[init_var]   t[i].action = 41   LHS receiver='t[i]'   RHS LITERAL 41
[init_var]   t[i].fn = h2       LHS receiver='t[i]'   RHS METHOD_REF h2
[init_alias] e->action = 41     LHS receiver='e'      RHS LITERAL 41
[init_alias] e->fn = h1         LHS receiver='e'      RHS METHOD_REF h1
```

**Conclusion:** slot identity is available from the AST as the receiver
sub-expression (everything left of the final member). Correlating the two writes
is `receiver-code equality within one method` — no DFG required for the
constant-index case, and syntactically sufficient for `t[i]` and `e->` too.

### Probe 2 — registrar calls (direct + two-level)

`cpg.call_target` already resolves both levels, and args/params are exposed:

```
call 'register_handler(41, h)' in init
    call_target -> register_handler (resolved=True)
    arg[1] LITERAL 41 ; arg[2] METHOD_REF h
    callee params: [(a,1), (f,2)]
call 'store(n++, a, f)' in register_handler
    call_target -> store (resolved=True)
    arg[1] n++ ; arg[2] IDENTIFIER a ; arg[3] IDENTIFIER f
    callee params: [(slot,1), (a,2), (f,3)]
```

**Conclusion:** resolved call targets + parameter-index alignment are already
present. Following `register_handler → store` needs only `call_target` and
arg→param index mapping — **no call-graph traversal engine and no points-to**.

---

## Producer 1 — correlated field store  → `REGISTRATION_ASSIGN`

**Goal:** recover `{action, callback}` when a table slot is populated by separate
field-assignment statements (`t[i].action = ID; t[i].fn = FN;`).

**Algorithm (AST + symbol resolution):**
1. Within each internal method, collect `<operator>.assignment` nodes whose LHS is
   a field access (`fieldAccess`/`indirectFieldAccess`).
2. Key each by `(method, receiver_code, )` where `receiver_code` = code of the LHS
   base sub-expression (probe 1). This is the **slot identity**.
3. Within a slot group, pair:
   - a write whose RHS is a `METHOD_REF` to an internal function → the **callback**;
   - a write whose RHS is an action id (numeric literal / enum-macro symbol) that
     matches a KB action → the **action id**.
4. Emit `ResolutionEvidence(kind=REGISTRATION_ASSIGN, callback=ref.target,
   action_id=…, match_strength=EXACT/RESOLVED/NORMALIZED per the id,
   provenance_group="site:reg:"+slot_key, nodes=[both assignments])`.
   **No handler selection** — the evidence flows into the calculus (weight 0.80).

**Supported slot forms & the AST/DFG boundary:**

| slot form | correlation | soundness |
|---|---|---|
| constant index `t[0]` | AST receiver-code equality | **sound with AST** |
| pointer alias `e->…` (both writes via `e`) | AST receiver-code equality on `e` | sound for the *pairing*; linking `e`→`t[1]` (which slot) needs alias/DFG, but pairing action↔callback does not |
| variable index `t[i]` | AST receiver-code equality (`t[i]`==`t[i]`) | **heuristic** — needs `i` unchanged between the two writes |

**Exact DFG boundary:** DFG (`REACHING_DEF`) is required **only** to *prove* the
variable-index case sound (no redefinition of the index between the two writes)
and to resolve an alias to a concrete slot. Baseline is AST + symbol resolution;
the DFG check is an escalation. Policy: emit at full `match_strength` when the
slot is a constant/among writes with no intervening index redefinition
(checkable via CFG order in one method); otherwise emit at a reduced
`match_strength` (NORMALIZED/HEURISTIC) so the calculus reflects the uncertainty
— not a hard drop.

Closes V2 directly; closes V5 because the frontend lowers the assignment-style
macro to the same field-assignments.

---

## Producer 2 — registrar call  → `REGISTRAR_CALL`

**Goal:** recover `{action, callback}` when registration goes through a registrar
function (`register_handler(ID, FN)`), possibly one more level (`→ store(...)`).

**Algorithm (resolved targets + param-index mapping; reuses producer 1):**
1. Find candidate registrar call sites: an internal `CALL` (resolved
   `call_target`) with **one arg a `METHOD_REF` to an internal function** and
   **another arg an action id** matching a KB action.
2. Confirm the callee actually *registers* the fn: map args→params by index, then
   inside the callee look for either
   - a correlated field store (producer 1) writing the fn-param into a callback
     slot and the id-param into the paired action slot; **or**
   - a further resolved call passing the fn-param onward (bounded depth, default
     2), recursing with the new arg→param map.
3. Emit `ResolutionEvidence(kind=REGISTRAR_CALL, callback=METHOD_REF.target,
   action_id=…, provenance_group="site:registrar:"+call_node, dispatch_site=…,
   nodes=[call, …])` (weight 0.70). **No handler selection.**

**Form handling:**

| form | first implementation |
|---|---|
| direct function `register_handler(id, fn)` writing params into a slot | **supported** (resolved target + producer 1 in callee) |
| two-level `register_handler → store` | **supported** (probe 2: both `call_target`s resolve; recurse with param map, depth ≤ 2) |
| function-pointer / aliased registrar (`reg_fn = register_handler; reg_fn(id,fn)`) | **deferred** — dynamic target, `call_target` unresolved |
| macro-generated call (`REGISTER(id,fn)` kept as `CALL:REGISTER`) | **deferred** — unexpanded, no resolved target |

**Interprocedural boundary (explicit):** the first implementation requires **only
resolved call targets (`cpg.call_target`) + parameter-index alignment**, bounded
to depth 2. It does **not** require a call-graph traversal framework, dynamic-call
linking, or points-to. Anything needing those (fn-pointer/alias/macro registrars)
is deferred and reported as `UNRESOLVED / UNSUPPORTED_REGISTRAR_CALL` as today.

Closes V3 and V6.

---

## Ordering & interaction

1. **Producer 1 first.** It is self-contained (AST + symbol resolution) and is the
   *slot-pairing primitive* producer 2 reuses inside a callee.
2. **Producer 2 second.** Adds only the call-site discovery + resolved-target
   recursion on top of producer 1.

Both are pure additions to the extractor set. The calculus is unchanged: their
evidence dedups, groups (`site:reg:` / `site:registrar:`), and aggregates exactly
like the existing producers. Existing weights already exist (`REGISTRATION_ASSIGN`
0.80, `REGISTRAR_CALL` 0.70).

---

## Open questions for producer-2 sign-off (before implementing it)

1. Recursion depth bound (proposed 2) — enough for real OCPP stacks, or make it a
   `CalculusConfig`-style knob?
2. What minimally qualifies a callee as a "registrar": must it reach a correlated
   field store, or is "an internal callee that receives `(id, internal METHOD_REF)`
   and stores the fn-param" sufficient (accepting the rare false positive)?
3. Whether to emit a low-strength `REGISTRAR_CALL` when the fn-param is passed on
   but the terminal store is not found within the depth bound (partial evidence),
   vs. emitting nothing.

Producer 1 has no open questions — the probe settles its boundary — so it can be
implemented directly on approval.

---

## Provenance

- Both probes run on the real embedded-Joern CPG (scratch fixtures
  `p3/fieldstore.c`, `p3/registrar.c`); outputs quoted verbatim above.
- No implementation or calculus change in this document.
