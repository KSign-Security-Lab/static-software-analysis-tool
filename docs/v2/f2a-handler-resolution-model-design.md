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

# Revised target schema (round 2)

A second review tightened three parts of the model: `action_id` was too narrow,
confidence must handle *contradiction* (not only corroboration), and
"unresolved" should be a status+reason rather than an evidence kind. The schema
below supersedes the sketch under "Convergence" above.

## Schema

```text
# ---- value object: the identity observed at a site (or declared in KB) ----
ActionIdentifier {
  protocol_string:   str?     # "RemoteStartTransaction"  (wire name / string literal)
  symbol:            str?     # "ACTION_REMOTE_START"     (enum/macro constant)
  numeric_id:        int?     # 15                         (integer id as written)
  normalized_name:   str?     # KB canonical action_name it maps to, once matched
  raw_expression:    str?     # raw CPG `code` of the id node ("ACTION_REMOTE_START", "0x0F", "msg->action")
  resolved_value:    int|str? # constant a symbol/macro resolves to (15), if resolvable
  node:              NodeRef?
}
# ONE matching function replaces today's scattered comparisons:
#   match(observed: ActionIdentifier, profile: ActionProfile) -> EXACT | WEAK | NONE
#   EXACT if numeric_id/resolved_value in profile.numeric_ids, symbol in profile.action_symbols,
#         protocol_string == profile.action_name, or normalized_name == profile.action_name
#   WEAK  if symbol/raw_expression *contains* a profile token (today's substring behavior)

# ---- one piece of evidence linking an action id (and/or dispatch site) to a callback ----
ResolutionEvidence {
  kind:           EvidenceKind
  action_id:      ActionIdentifier      # may be partial (some fields null)
  callback:       MethodRef?            # None when evidence is only a dispatch site
  dispatch_site:  NodeRef?              # the indirect-call / switch node, if any
  nodes:          [NodeRef]             # supporting CPG nodes
  weight:         float                 # PRIOR reliability of this KIND
  match_strength: EXACT | WEAK
  extractor:      str                   # provenance
}
EvidenceKind = STRING_DISPATCH | ENUM_CASE | REGISTRATION_INIT | REGISTRATION_ASSIGN
             | REGISTRAR_CALL | NAME_MATCH | VTABLE_SLOT | FACTORY_RETURN | DISPATCH_SITE

# ---- candidate = all evidence agreeing on one callback ----
HandlerCandidate { callback: MethodRef, evidence: [ResolutionEvidence], confidence: float }

# ---- outcome of selection over all candidates ----
SelectionResult {
  status:     RESOLVED | AMBIGUOUS | UNRESOLVED
  chosen:     HandlerCandidate?     # iff RESOLVED
  candidates: [HandlerCandidate]    # all, ranked desc
  conflict:   ConflictReport?       # whenever ≥2 competing callbacks existed (even if RESOLVED)
  unresolved: UnresolvedReport?     # iff UNRESOLVED
}
ConflictReport   { competing: [{callback, confidence, evidence_kinds}], margin: float, note: str }
UnresolvedReport { reason: UnresolvedReason, dispatch_site: NodeRef?,
                   attempted_extractors: [str], available_evidence: [ResolutionEvidence] }
UnresolvedReason = NO_EVIDENCE | EXTERNAL_DEFINITION | DYNAMIC_ACTION_ID | MISSING_POINTSTO
                 | UNRESOLVED_INDIRECT_CALL | GENERATED_CODE_UNAVAILABLE | REGISTRATION_OUT_OF_TU
```

- **Q1 (identity):** `ActionIdentifier` is the single home for identity; every
  extractor fills the fields it can observe, and one `match()` replaces today's
  per-strategy `literal == action` / symbol-token / numeric checks. `mechanism`
  is gone — it is now `evidence.kind`.
- **Q3 (unresolved):** "could not resolve" is a **status + reason + dispatch_site
  + attempted_extractors**, never a fake evidence kind. `DISPATCH_SITE` is a real
  evidence kind (an indirect call with no binding); the *inability to bind* is a
  status that carries the site as provenance.

## Confidence semantics

**Ordinal, bounded score in `[0, 0.99]` — explicitly NOT a calibrated
probability** (no labeled corpus to calibrate against; it would be false
precision). It exists to rank candidates and hint F6.

Per-kind **weight** (priors == today's hardcoded confidences, so behavior is
preserved):

| Kind | weight |
|---|---|
| STRING_DISPATCH | 0.90 |
| ENUM_CASE | 0.85 |
| REGISTRATION_INIT / REGISTRATION_ASSIGN | 0.80 |
| REGISTRAR_CALL | 0.70 |
| NAME_MATCH (pattern) | 0.70 |
| NAME_MATCH (token) | 0.65 |

- **Per-evidence score** = `weight × (1.0 if EXACT else 0.85)`.
- **Corroboration** (same callback): noisy-OR *shape* (monotonic, capped, order
  independent — not a probability): `confidence = min(0.99, 1 − Π_i (1 − score_i))`.
  e.g. `ENUM_CASE(0.85)` + `NAME_MATCH(0.70)` → `1 − 0.15·0.30 = 0.955`.
- **Contradiction** (different callbacks): competitors, never merged. A
  `ConflictReport` is emitted whenever ≥2 candidates exist — even when we still
  resolve — so disagreement is always visible.
- **Tie / ambiguity policy** (`AMBIGUITY_MARGIN = 0.15`, `MIN_CONFIDENCE = 0.50`):

  ```
  0 candidates                    -> UNRESOLVED (reason from extractors; default NO_EVIDENCE)
  1 candidate,  conf >= floor      -> RESOLVED
  1 candidate,  conf <  floor      -> RESOLVED (flagged low); policy-tunable to UNRESOLVED
  >=2, margin >= AMBIGUITY_MARGIN  -> RESOLVED top1 + ConflictReport (runner-up recorded)
  >=2, margin <  AMBIGUITY_MARGIN  -> AMBIGUOUS (chosen=None) + ConflictReport(close set)
  ```

  Worked example (registration→foo 0.80, name→foo 0.70, switch→bar 0.85):
  foo corroborates to `1 − 0.2·0.3 = 0.94`, bar `0.85`, margin `0.09 < 0.15`
  → **AMBIGUOUS**. The two authoritative kinds (registration vs switch) disagree;
  the margin rule surfaces that instead of letting a weak name match tip it.

## Concrete outcomes (one JSON each)

**RESOLVED (corroboration)** — DataTransfer via enum case, handler name also matches:

```json
{
  "status": "RESOLVED",
  "chosen": {
    "callback": {"method": "handle_data_transfer", "file": "dt.c", "line": 22},
    "confidence": 0.955,
    "evidence": [
      {"kind": "ENUM_CASE", "extractor": "enum_case",
       "action_id": {"symbol": "ACTION_DATA_TRANSFER", "normalized_name": "DataTransfer",
                     "raw_expression": "case ACTION_DATA_TRANSFER:", "node": 81604378624},
       "callback": {"method": "handle_data_transfer"}, "weight": 0.85, "match_strength": "EXACT",
       "nodes": [81604378624, 30064771084]},
      {"kind": "NAME_MATCH", "extractor": "name_pattern",
       "action_id": {"normalized_name": "DataTransfer", "raw_expression": "handle_data_transfer"},
       "callback": {"method": "handle_data_transfer"}, "weight": 0.70, "match_strength": "EXACT",
       "nodes": [111669149700]}
    ]
  },
  "candidates": ["<chosen above>"],
  "conflict": null,
  "unresolved": null
}
```

**AMBIGUOUS** — contradiction between authoritative kinds:

```json
{
  "status": "AMBIGUOUS",
  "chosen": null,
  "candidates": [
    {"callback": {"method": "foo"}, "confidence": 0.94,
     "evidence": [
       {"kind": "REGISTRATION_INIT", "callback": {"method": "foo"}, "weight": 0.80,
        "match_strength": "EXACT", "action_id": {"symbol": "ACTION_X", "numeric_id": 7}},
       {"kind": "NAME_MATCH", "callback": {"method": "foo"}, "weight": 0.70,
        "match_strength": "EXACT", "action_id": {"normalized_name": "ActionX"}}
     ]},
    {"callback": {"method": "bar"}, "confidence": 0.85,
     "evidence": [
       {"kind": "ENUM_CASE", "callback": {"method": "bar"}, "weight": 0.85,
        "match_strength": "EXACT", "action_id": {"symbol": "ACTION_X", "raw_expression": "case ACTION_X:"}}
     ]}
  ],
  "conflict": {
    "competing": [
      {"callback": "foo", "confidence": 0.94, "evidence_kinds": ["REGISTRATION_INIT", "NAME_MATCH"]},
      {"callback": "bar", "confidence": 0.85, "evidence_kinds": ["ENUM_CASE"]}
    ],
    "margin": 0.09,
    "note": "authoritative kinds disagree (REGISTRATION_INIT->foo vs ENUM_CASE->bar); margin 0.09 < 0.15"
  },
  "unresolved": null
}
```

**UNRESOLVED** — RemoteStart registrar-call (V3): dispatch site exists, no wired
extractor produced a callback-bearing evidence:

```json
{
  "status": "UNRESOLVED",
  "chosen": null,
  "candidates": [],
  "conflict": null,
  "unresolved": {
    "reason": "UNRESOLVED_INDIRECT_CALL",
    "dispatch_site": {"node": 30064771118, "code": "g_registry[i].fn(frame->payload)",
                      "file": "remote_start.c", "line": 36, "kind": "<operator>.pointerCall"},
    "attempted_extractors": ["string_dispatch", "enum_case", "registration_ast", "name_match"],
    "available_evidence": [
      {"kind": "DISPATCH_SITE", "callback": null, "dispatch_site": {"node": 30064771118},
       "action_id": {"raw_expression": "frame->action"}, "weight": 0.0, "match_strength": "NONE",
       "extractor": "dispatch_site_finder", "nodes": [30064771118]}
    ]
  }
}
```

(The cross-TU variant is identical with `reason: "EXTERNAL_DEFINITION"`; a
runtime-computed id is `"DYNAMIC_ACTION_ID"`.)

## Mapping the current four strategies (behavior preservation)

| Today's strategy | Producer | `kind` | `ActionIdentifier` filled | weight | callback from |
|---|---|---|---|---|---|
| string dispatch | `StringDispatchExtractor` | `STRING_DISPATCH` | `protocol_string` = literal | 0.90 | call in the literal's branch |
| enum/switch | `EnumCaseExtractor` | `ENUM_CASE` | `symbol` (+`resolved_value` if macro→int) | 0.85 | first internal call via CFG from case |
| registration (init/assign) | `RegistrationAstExtractor` | `REGISTRATION_INIT`/`REGISTRATION_ASSIGN` | `symbol` and/or `numeric_id` | 0.80 | `METHOD_REF` target |
| name fallback | `NameMatchExtractor` | `NAME_MATCH` | `normalized_name` / `symbol` | 0.70 / 0.65 | the method itself |

Behavior preservation is a property of the **selection policy**, in two phases:

- **Phase 1 — cascade-compatible mode:** consider evidence in weight-tier order
  (0.90 → 0.85 → 0.80 → 0.70) and stop at the first tier that yields a candidate.
  On every current fixture only one strategy fires per action → exactly one
  candidate, `confidence == weight`, identical evidence → all 20 tests stay green.
  This is the safe structural pivot.
- **Phase 2 — corroborate+contradict mode:** *not* assertion-preserving, and
  flagged deliberately. `data_transfer_enum.c`'s handler `handle_data_transfer`
  matches **both** `ENUM_CASE` and the DataTransfer `NAME_MATCH` patterns; under
  corroboration its evidence set grows and confidence rises 0.85 → ~0.955,
  changing `test_enum_dispatch_handler_discovered`'s evidence-type assertion. That
  change is *correct* (two independent supports really exist), but enabling
  corroboration is an explicit, test-updating step, not a silent one.

Plan: keep the mode a selection-stage parameter so the structural pivot (phase 1)
and the policy change (phase 2) are reviewable — and revertable — separately.

---

## Provenance

- Design review only; no implementation change in this document.
- Q2 verified against the real embedded-Joern CPG (receiver-subtree identity
  probe, shown above). Other claims reference the shipped code
  (`_handler_by_registration`, the four-strategy cascade) and the 6-variant survey
  in `f2a-handler-registration-ir.md`.
