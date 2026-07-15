# F2-A — Phase 2 readiness: output-model integration before corroboration

**Follow-up to** [`f2a-handler-resolution-model-design.md`](./f2a-handler-resolution-model-design.md)
(Phase 1 shipped, commit `ada75ea`).

**Decision:** do **not** move directly to Phase 2 (corroboration + contradiction).
First surface the richer `SelectionResult` into `F2AResult`, otherwise
`AMBIGUOUS`, competing candidates, and structured unresolved reasons exist only
inside the analyzer and are lost when converted back to `HandlerMap` +
limitation strings. Output model first, policy second.

Revised order:

1. Surface `SelectionResult` / `ConflictReport` / `UnresolvedReport` in `F2AResult`.
2. Define evidence deduplication and `provenance_group` semantics.
3. Add adversarial conflict tests (real CPG fixtures).
4. Make `ActionIdentifier.consistency()` affect evidence selection explicitly.
5. Then enable corroboration and contradiction (Phase 2).
6. Then implement the correlated-field-store and registrar-call extractors.

---

## Open questions resolved before Phase 2

Each answer is marked **current behavior** (a fact about shipped code) or
**decision** (to lock in before Phase 2).

### 1. Does `select_cascade` run all extractors, or stop at the first tier?

**Current behavior: runs all four, records conflicts, preserves the highest-tier
choice.** `_resolve_handler` collects evidence from every extractor;
`select_cascade` picks the max-weight candidate and rebuilds the `HandlerMap`
from that single evidence. Proof: the `UpdateFirmware` candidate returns carrying
**both** `STRING_DISPATCH` and `NAME_MATCH` evidence (all extractors ran) while
the `HandlerMap` stays string-tier at 0.9.

Nuance: "cascade-compatible" preserves the *chosen handler and HandlerMap*, not
the old *execution* (which stopped at the first tier). We now always do the extra
work — which is what makes competing candidates visible for `AMBIGUOUS`.

### 2. Deduplication key for overlapping extractors on the same callback + site

**Current behavior: the only grouping key is `callback`; no finer dedup** — two
extractors emitting for one callback both stay in the evidence list. Harmless
under cascade (confidence = max), but must be defined before corroboration.

**Decision — two levels:**
- **Exact-duplicate collapse:** `(kind, callback, dispatch_site, tuple(sorted(nodes)))`.
  Identical evidence from two paths becomes one. Different *kinds* for the same
  callback are **not** duplicates — distinct signals, retained.
- Independence is handled at aggregation via `provenance_group` (below), not by
  dedup.

### 3. How `provenance_group` affects confidence aggregation

**Current behavior: unused** (cascade ignores it). **Decision for Phase 2:**
- Partition a candidate's evidence by `provenance_group`; take the **max score
  within a group** (same underlying signal — never double-count), then
  **noisy-OR across distinct groups** (independent signals — corroborate).
- The `ENUM_CASE` + `NAME_MATCH` independence concern is encoded in the group
  key: evidence is independent only if it comes from a **different CPG site *and*
  a different identifier field**. Enum matched via `symbol` at the switch site
  and a name matched via `normalized_name` at the function decl are two groups
  (weakly independent, corroborate but capped); if both reduce to the *identical
  normalized token* with no other signal, they collapse into one group. The
  precise key is finalized in item 2 with fixtures.

### 4. Internally conflicting `ActionIdentifier`: discard / penalize / flag / force ambiguity?

**Decision: flag + penalize. Never silently discard; never force global
ambiguity.**
- If `consistency(kb) == CONFLICTING`, flag the evidence and demote it (cap
  `match_strength` at `HEURISTIC_SUBSTRING`, reduce `score`); keep it (F6 needs
  the provenance).
- If that evidence is a candidate's *sole* support, its low score naturally risks
  falling below `MIN_CONFIDENCE` → contributes to `UNRESOLVED`/low with no
  special case.
- Not forcing ambiguity: ambiguity is about competing *callbacks*; a messy
  *identifier* is a per-evidence quality issue. Conflating them would let one bad
  observation nuke a well-supported result. The conflict is surfaced, not
  dropped. (This is item 4 of the order — it defines how `consistency()` feeds
  selection.)

### 5. Can the public output represent an ambiguous handler without selecting one?

**Current behavior: no.** A `HandlerMap` is appended only on `RESOLVED`;
`AMBIGUOUS`/`UNRESOLVED` collapse to a limitation string and the internal
`SelectionResult` is dropped. Fixing this is increment 1. Proposed shape:

```text
# public, serializable (models.py) — node ids resolved to names/files/lines
HandlerResolution {
  action: str
  status: "RESOLVED" | "AMBIGUOUS" | "UNRESOLVED"
  chosen: HandlerRef?                       # iff RESOLVED
  candidates: [ HandlerCandidateView {      # ranked; present for RESOLVED and AMBIGUOUS
      function, file, line, confidence,
      evidence_kinds: [str],
      action_id_consistency: "CONSISTENT" | "CONFLICTING" | "PARTIAL",
  } ]
  conflict: { competing:[{function,confidence,evidence_kinds}], margin, note }?
  unresolved: { reason, secondary?, dispatch_site:{file,line,code}?, attempted_extractors:[str] }?
}

F2AResult:
  handler_maps: [HandlerMap]                 # UNCHANGED — populated only on RESOLVED (back-compat)
  handler_resolutions: [HandlerResolution]   # NEW — one per action, covers all three outcomes
```

`AMBIGUOUS` becomes a first-class `handler_resolutions` entry with `chosen=null`,
ranked candidates, and the `ConflictReport` — no handler selected, nothing lost.
The internal `SelectionResult` (node ids) maps to this public view
(names/files/lines) at assembly time, keeping the graph-typed model separate from
the serializable one.

---

## Adversarial CPG fixtures to add (before switching policies)

All six are constructible as real CPGs. Some cannot fire until the Phase-3
extractors exist and will assert the unresolved/limitation path for now.

| Fixture | Fires today? | Phase-1 assertion |
|---|---|---|
| registration→foo vs switch→bar | **yes** | two competing candidates; cascade picks switch/bar (0.85 > 0.80); `ConflictReport` records both |
| duplicate registrations for one action | needs extractor to emit all matches | ≥2 evidences / candidates for one action |
| same registration seen by two extractors | partial | exact-dup collapse (key from Q2) → one evidence |
| exact numeric registration vs weak name match | **yes** | competing candidates; registration (0.80, EXACT) vs name (0.65, HEURISTIC) |
| conflicting symbol vs resolved numeric | yes (unit already) | `consistency()==CONFLICTING`; + a CPG fixture on the extractor path |
| two candidates within the ambiguity margin | yes | with corroboration OFF this still resolves; documents the Phase-2 flip point |

Exposed gap: the registration extractor currently returns the **first** match, so
"duplicate registrations" and some competing cases need it to emit **all**
matches into the candidate set — a contained change (yield vs return-first)
belonging to this increment.

---

## Proposed next increment (output-model integration + adversarial tests)

1. Public `HandlerResolution` model + map `SelectionResult` → it at assembly; add
   `handler_resolutions` to `F2AResult`; keep `handler_maps` unchanged.
   `AMBIGUOUS`/`UNRESOLVED` become representable.
2. Registration extractor emits **all** matches (needed for duplicate/competing
   fixtures).
3. Six adversarial CPG fixtures + tests asserting the **public**
   `handler_resolutions` shape — under the current cascade policy (no
   corroboration).
4. Leave dedup-key finalization (Q2/Q3) and `consistency()`-penalty wiring (Q4)
   as their own items; Phase 2 (corroborate + contradict) strictly after.

**Status:** Phase 1 approved. This document defines the next increment
(output-model integration + adversarial tests). Corroboration/contradiction
(Phase 2) is enabled only after the public result can represent RESOLVED,
AMBIGUOUS, and UNRESOLVED cleanly.

---

## Provenance

- Design/planning; no implementation change in this document.
- Q1/Q2 "current behavior" answers are backed by the Phase-1 verification run
  (the `UpdateFirmware` candidate carrying both `STRING_DISPATCH` and
  `NAME_MATCH` evidence) and the shipped code in `ssat/f2a/resolution.py` and
  `pipeline.py` (commit `ada75ea`).
