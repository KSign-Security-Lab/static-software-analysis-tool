# F2-A Handler Resolution — model design review

**Follow-up to** [`f2a-handler-registration-ir.md`](./f2a-handler-registration-ir.md).

That refactor introduced a `HandlerRegistration` IR with two AST extractors.
Four design questions were then raised about whether the IR is the *right*
abstraction. This document records the answers and the resulting target model.
All four questions converge on one refactor.

One empirical claim below (Q2) was verified against the real CPG rather than
asserted; the probe result is included.

---

## 1. `mechanism` is provenance, not semantics

`mechanism` (`AGGREGATE_INIT | INDEXED_ASSIGN | …`) names *how* the fact was
recovered, not *what* it means. The semantic content of the fact is only
`(action_id, callback)`.

The tell that it is misplaced: **the consumer never branches on it.**
`_handler_by_registration` matches on `action_id_symbols` / `action_id_literals`
and ignores `mechanism` entirely. A field the semantic consumer never reads is by
definition not semantic — it is debugging/provenance metadata.

**Correction:** fold it into a structured evidence object and *derive* confidence
from the evidence rather than storing a mechanism tag:

```
evidence: ResolutionEvidence { kind: AGGREGATE_INIT|INDEXED_ASSIGN|…, nodes: [...], file, line }
```

F6 wants exactly this evidence object for provenance anyway.

---

## 2. V2 (separate assignments) does not require full DFG

Claim under test: correlated assignments to the same slot can be recovered from
**AST + symbol resolution**, without dataflow.

**Verified.** For `g_table[0].action = ACTION_REMOTE_START;` and
`g_table[0].fn = process_request;` the CPG shows both LHS field accesses share a
**structurally identical receiver subtree**:

```
assignment: 'g_table[0].action = ACTION_REMOTE_START'
   LHS fieldAccess member : 'g_table[0].action'
   LHS receiver subtree   : 'g_table[0]'   (label=CALL, indirectIndexAccess)
   RHS                    : CALL 'ACTION_REMOTE_START'
assignment: 'g_table[0].fn = process_request'
   LHS fieldAccess member : 'g_table[0].fn'
   LHS receiver subtree   : 'g_table[0]'   (label=CALL, indirectIndexAccess)
   RHS                    : METHOD_REF 'process_request'
```

So the extractor is: *group assignments whose receiver sub-expression (everything
left of the final member) is structurally equal, then merge the ids/refs found
across the group.* Pure AST + symbol resolution.

DFG is only an **escalation** for unsound subcases, not a baseline:

- **variable index** — `t[i].action=…; t[i].fn=…` in a loop: `t[i] == t[i]`
  syntactically, but soundness needs `i` unchanged between the stores
  (SSA / no-redef). Acceptable as a heuristic with a confidence penalty; DFG
  upgrades it to sound.
- **aliasing** — `Reg *e = &t[0]; e->action=…; e->fn=…`: receivers differ
  syntactically (`e` vs `t[0]`); only alias/points-to closes that.

Net: the correlated-field-store extractor is **AST-first, DFG-optional** — cheaper
than originally implied, and it also covers the macro-to-assignment shape (V5).

---

## 3. The umbrella concept is `HandlerResolutionEvidence`, not `HandlerRegistration`

Registration is one *kind* of resolution; it presumes an explicit registration
site. Cases with no such site:

- **Virtual dispatch / struct-of-fn-ptrs** — resolved by object type / vtable
  slot. (Partly overlaps registration: `obj->ops.on_action = fn` *is* an
  assignment; a true C++ vtable resolves by type, with no visible store.)
- **Factory-generated callbacks** — the binding is the factory's return logic;
  resolution = the set of methods it can return (needs return-set / points-to;
  inherently multi-candidate, lower confidence).
- **Cross-TU / linker-section / codegen tables** — no local evidence at all.

The unifying concept: **evidence that a dispatch site (or action) resolves to a
candidate callback**, whatever its form. This also **subsumes the string / enum /
name strategies** — today each ad-hoc returns `(callee, evidence, confidence)`;
under the general model they are simply resolution-evidence producers of a
different `kind`. Registration stops being special-cased.

Two consequences to bank now:

- Represent **"resolution attempted, evidence absent / external"** as a
  first-class value (`kind: EXTERNAL_UNRESOLVED`) instead of a flat limitation
  string. That is the cross-TU case, and F6 needs "saw a dispatch site, could not
  bind here" distinct from "never looked."
- The dispatch **site** itself (`g_registry[i].fn(payload)`,
  `handlers[action](…)`, the unlinked `<operator>.pointerCall` Joern already
  flags) is evidence and should be a node in the model — the anchor that says "an
  indirect handler is invoked here," independent of whether registration is
  found.

---

## 4. Candidates + a selection stage, not direct binding

Binding to a single `callback_method` at extraction time fuses extraction with
selection and does not scale. Target pipeline:

```
extractors → HandlerResolutionEvidence[]              (per producer, may overlap)
           → group by callback → HandlerCandidate[] { callback, evidence[], confidence }
           → selection stage → chosen | top-k | AMBIGUOUS | UNRESOLVED
```

Why it matters in real code: multiple registrations for one id (override /
duplicate); a factory with several possible returns; and — the valuable case —
**corroboration across kinds**: a name-match *and* a registration *and* a
switch-dispatch all pointing at the same function should raise confidence above
any single one. Direct binding discards that signal.

The current cascade is a degenerate selection stage (most-precise-first, stop at
first hit). That is a fine *policy*, but it is hardwired into control flow. Making
candidates first-class makes the policy explicit and enables corroboration
instead of short-circuiting.

---

## Convergence

All four answers are one refactor seen from four sides:

```
HandlerRegistration { mechanism, callback_method, ... }                         # today
        |
        v   Q1 (kind, not mechanism)   Q3 (general umbrella)
HandlerResolutionEvidence { kind, action_id, callback?, dispatch_site?, nodes, confidence }
        |   group by callback
        v   Q4 (candidates)
HandlerCandidate { callback, evidence[], confidence }
        |   selection stage: corroborate, rank, or report AMBIGUOUS / UNRESOLVED
        v
chosen handler
```

with `mechanism → evidence.kind` (Q1), the V2 extractor AST-structural (Q2),
string/enum/name folding in as evidence producers (Q3), and confidence *derived*
from the evidence set rather than hardcoded `0.8`.

---

## Recommended order (modeling ≠ implementing)

1. **Now (small, safe):** move `mechanism` into an `evidence` field on the
   existing dataclass (Q1) — pure cleanup, no behavior change.
2. **Next increment:** introduce `HandlerCandidate` + a thin selection stage that
   initially just implements "most-precise-first" (Q4), and make the existing
   four strategies emit candidates into it. This is the structural pivot;
   behavior-preserving if selection replicates the current cascade order.
3. **Then:** rename the umbrella to `HandlerResolutionEvidence`, add the AST
   correlated-field-store extractor (Q2 → V2/V5), then the call-graph registrar
   extractor (V3/V6), and add the explicit `EXTERNAL_UNRESOLVED` value (Q3).

**Caution against over-building:** virtual-dispatch and factory resolution need
points-to / return-set analysis the current CPG layer does not expose cheaply.
Represent them in the model now (so the type is future-proof) but do not
implement those extractors until a real OCPP codebase needs them. Modeling the
kinds is free; implementing every extractor is not.

---

## Provenance

- Design review only; no implementation change in this document.
- Q2 verified against the real embedded-Joern CPG (receiver-subtree identity
  probe, shown above). Other claims reference the shipped code
  (`_handler_by_registration`, the four-strategy cascade) and the 6-variant survey
  in `f2a-handler-registration-ir.md`.
