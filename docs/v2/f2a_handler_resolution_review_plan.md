# F2-A · Handler Resolution — Technical Design Review

**Format:** research-conference technical review · 18 slides
**Audience:** engineers & security researchers fluent in static analysis, AST/CPG, protocol analysis
**Style rules:** one idea per slide · minimal text · boxes-and-arrows over prose · diagrams must be technically accurate · assume adversarial Q&A

> Framing note carried through the whole deck: F2-A produces **evidence-backed candidates**, not confirmed facts. It resolves *which source function handles a protocol action*; it never claims a vulnerability. Every claim is traceable to a file/line record. Keep this honesty visible on every slide that states a result.

---

## Slide 1 — Title & Thesis

- **Goal:** Set the frame: this is an *evidence-based resolution* subsystem, not a heuristic matcher.
- **Main message:** F2-A recovers the protocol-action → source-handler mapping that dynamic dispatch erases, and does it with an auditable evidence calculus.
- **Suggested diagram:** One-line pipeline strip with F2-A highlighted:
  `KB → [F2-A: action ↦ handler] → field binding → dataflow → sinks → findings`
- **Bullets:**
  - F2-A = "Handler Resolution" stage of an OCPP-aware static pipeline
  - Input: protocol knowledge + a code property graph. Output: per-action resolution + evidence trail
  - Contribution: evidence model + calculus + explicit "refuse to guess" semantics
- **Speaker notes:** State the one-sentence thesis and the honesty contract up front. Everything downstream trusts F2-A's mapping, so F2-A must either be right or *say it doesn't know*. Preview that the talk's spine is: problem → evidence → calculus → decision → limits.

---

## Slide 2 — Motivation: Why Handler Resolution Exists

- **Goal:** Justify the subsystem before any mechanism.
- **Main message:** Protocol semantics live in a spec; the code that enforces them is reached only through indirection — someone has to connect the two.
- **Suggested diagram:** Two disconnected columns joined by a "?" bridge:
  ```
  PROTOCOL WORLD                 CODE WORLD
  "RemoteStartTransaction"  --?-->  remote_handler()
  "SetChargingProfile"      --?-->  ??? 
  action semantics                 functions, tables, callbacks
  ```
- **Bullets:**
  - Security questions are phrased over *protocol actions*, not functions
  - The handler is the entry point where untrusted payload first becomes program state
  - Without the mapping, every later analysis has no anchor to start from
- **Speaker notes:** Concrete stakes: to ask "is the charging-profile limit validated?", you must first know *which function* processes SetChargingProfile. That function is the taint source root. The mapping is the precondition for asking any protocol-aware question.

---

## Slide 3 — The Core Difficulty: Dispatch Breaks the Call Graph

- **Goal:** Explain *why the mapping is hard* — the research problem.
- **Main message:** Handlers are invoked through function pointers / dispatch tables, so the static call graph does not contain the edge we need.
- **Suggested diagram:** Call graph with the critical edge missing:
  ```
  dispatch(frame) --calls--> (*table[i].fn)()   ← indirect: NO static edge to remote_handler
  registration:  table[k] = { ACTION, remote_handler }   ← the edge lives HERE, in data
  ```
- **Bullets:**
  - Dynamic dispatch ⇒ the caller→handler edge is absent from the CG
  - The real binding is expressed in *data* (registration sites), not control flow
  - So we must recover the edge from **registration structure + identifier matching**, not from calls
- **Speaker notes:** This is the crux. A naive call-graph walk fails by construction. The binding is latent in initializer tables, assignments, and registrar calls. F2-A's job is to reconstruct that latent edge statically. Anticipate: "why not just run it?" — static, pre-deployment, whole-firmware, no harness.

---

## Slide 4 — F2-A in the Larger Pipeline

- **Goal:** Locate F2-A precisely; show it is one stage with hard dependents.
- **Main message:** F2-A is a gate: nothing protocol-aware downstream can start until it resolves.
- **Suggested diagram:** Vertical pipeline, F2-A boxed, dependents shaded:
  ```
  Protocol Knowledge Base
        ↓
  Action Definitions
        ↓
  ┌───────────────────────┐
  │ Handler Resolution — F2-A │  ← this talk
  └───────────────────────┘
        ↓  (resolved action ↦ handler)
  Field Binding → Flow Candidates → Sink Mapping
        → Expected-Check Matching → Vulnerability Analysis (F6)
  ```
- **Bullets:**
  - Upstream: KB + action definitions describe *what to look for*
  - F2-A: turns actions into concrete code anchors
  - Downstream: everything consumes the anchor; F6 makes the final judgment
- **Speaker notes:** Emphasize separation of concerns: F2-A does not do taint, sinks, or checks. It deliberately stops at "here is the handler and why". A wrong resolution poisons everything after it — hence the conservative bias introduced later.

---

## Slide 5 — Inputs

- **Goal:** Enumerate what F2-A consumes and what each contributes.
- **Main message:** Two knowledge sources meet: protocol truth (KB) and code structure (CPG/AST/symbols).
- **Suggested diagram:** Fan-in into F2-A:
  ```
  Protocol KB ─┐   (action names, symbol constants, numeric ids, aliases)
  CPG/AST ─────┼──► F2-A
  Symbols ─────┘   (function definitions, internal vs external)
  ```
- **Bullets:**
  - **Protocol KB** — per-action profile: wire name, macro/enum symbols, numeric ids, name aliases
  - **CPG/AST** — structural shape of initializers, assignments, calls, dispatch sites
  - **Symbol info** — which references resolve to internal functions (candidate callbacks)
  - **Action identifiers** — the tokens that must match between code and protocol
- **Speaker notes:** The KB is the ground truth of "what identifiers denote which action". The AST supplies the *shape* of registration; symbols tell us a reference is a real internal function, not an external stub. Matching happens in the overlap of KB tokens and code identifiers.

---

## Slide 6 — Registration Mechanisms: A Taxonomy

- **Goal:** Show the diversity of real-world registration syntax.
- **Main message:** There is no single "registration" construct; firmware binds handlers many ways, so recognition must be plural.
- **Suggested diagram:** A grid of mini code shapes, each labeled:
  ```
  aggregate init      { ACTION, fn }
  designated init     { .action = ACTION, .fn = fn }
  indexed assign      handlers[ACTION] = fn
  correlated stores   t[k].action = ACTION;  t[k].fn = fn
  registrar call      register(ACTION, fn)              → callee stores it
  delegated registrar register(...) → store_handler(...) → t[.] = fn
  ```
- **Bullets:**
  - Same semantic ("bind action ↦ handler"), many syntactic forms
  - Forms differ in *where the id and callback are* and *how they correlate*
  - Some resolve at initialization; some require following a call into a callee
- **Speaker notes:** Stress semantic equivalence vs syntactic divergence. The designated and positional aggregate forms are semantically identical but structurally different in the AST (designated members are wrapped assignments). This diversity is exactly why one universal matcher would be brittle.

---

## Slide 7 — Why Multiple Extractors, Not One Matcher

- **Goal:** Defend the multi-extractor architecture.
- **Main message:** Each mechanism has its own correlation key; folding them into one rule sacrifices precision and diagnosability.
- **Suggested diagram:** Many extractors → one shared evidence bus:
  ```
  [aggregate] [designated] [indexed] [correlated] [registrar] [delegated] [name]
        \        \        |        /        /         /        /
         ▼        ▼       ▼       ▼        ▼         ▼        ▼
                  ┌──────────────────────────────┐
                  │   uniform Evidence stream     │
                  └──────────────────────────────┘
  ```
- **Bullets:**
  - Different mechanisms correlate id↔callback differently (same node / sibling field / shared slot / arg→param)
  - Independent extractors ⇒ independent evidence ⇒ *corroboration* is possible
  - A miss in one extractor is a precise diagnostic, not a silent whole-system failure
- **Speaker notes:** Key architectural claim: extractors are **recognizers, not deciders**. They emit into a common evidence model. This is what lets two mechanisms agree on one handler and raise confidence, and lets us attribute an unresolved case to a specific mechanism's limit.

---

## Slide 8 — Registration Extractors (Capability Map)

- **Goal:** One-glance capability table; pattern / evidence / strength / limit per extractor.
- **Main message:** Each extractor has a crisp recognized shape and an explicit boundary.
- **Suggested diagram:** 4-column table:
  ```
  Extractor        Recognizes                 Emits            Boundary
  aggregate init   { ID, fn }                 REGISTRATION_INIT inline id only
  designated init  { .a=ID, .fn=fn }          REGISTRATION_INIT same struct init
  indexed / field  h[ID]=fn ; t[k].*=…        REGISTRATION_ASSIGN shared slot key
  registrar call   f(ID, fn) → stores fn      REGISTRAR_CALL     must reach store
  delegated        f→g→ store (arg→param)     REGISTRAR_CALL     depth-bounded (2)
  dispatch/name    switch(id)/name similarity ENUM_CASE/NAME_MATCH weak, corroborative
  ```
- **Bullets:**
  - Strong, structural extractors carry high prior weight
  - Name/dispatch signals are weak — usable only as corroboration
  - Every extractor's boundary is a named limitation, surfaced downstream
- **Speaker notes:** Walk one row (designated): correlation is "same enclosing initializer, order-independent, no field-name guessing". Contrast registrar: needs to follow the call into the callee and reach the terminal store, else it emits nothing and reports the miss. Boundaries are deliberate, not accidental.

---

## Slide 9 — The Evidence Model

- **Goal:** Define the currency of the system.
- **Main message:** Extractors speak one language: a structured evidence record with provenance and a source trail.
- **Suggested diagram:** One evidence record, exploded:
  ```
  Evidence {
    action id     ─ symbol / numeric / raw expr  (+ match strength)
    callback      ─ the resolved internal function
    kind          ─ which mechanism produced it
    provenance    ─ site/group key (dedup + grouping)
    confidence    ─ prior weight × match multiplier
    dispatch site ─ where the binding is observed
    records[]     ─ ordered file/line trail (auditable)
  }
  ```
- **Bullets:**
  - Evidence is *typed by mechanism* and *scored by match quality*
  - Provenance key makes duplicates and same-site evidence identifiable
  - Records preserve the original source expressions and locations
- **Speaker notes:** Emphasize match strength: exact identifier vs normalized vs heuristic substring vs name-only. A record trail is not decoration — it is what makes a resolution reviewable by a human who did not run the tool. Multiple extractors emit simultaneously because they observe independent facts about the same binding.

---

## Slide 10 — Evidence Calculus: Merging Independent Signals

- **Goal:** Explain how many evidences become one confidence per candidate.
- **Main message:** Combine *within a site* by max (no double counting) and *across independent sites* by corroboration (noisy-OR), then apply caps and penalties.
- **Suggested diagram:** Two-stage combination:
  ```
  evidences ─► group by provenance
     within group:  confidence = MAX (same site ≠ new information)
     across groups: noisy-OR    (independent corroboration raises belief)
                        │
                        ▼
     caps (weak-only ≤ .85, global ≤ .99) · conflict penalty
                        │
                        ▼
              candidate confidence
  ```
- **Bullets:**
  - Priors per kind (structural > dispatch > name); exact match preserved, heuristic discounted
  - Same-site duplicates collapse; independent sites corroborate
  - Weak-only evidence is capped; conflicting competitors are penalized
- **Speaker notes:** Give the intuition and the numbers the audience will ask for: representative priors (structural registration ≈ 0.80, registrar ≈ 0.70, name-match low), heuristic-substring multiplier (~0.7), ambiguity margin 0.15, acceptance floor 0.50, registrar depth 2. Stress *why noisy-OR*: two independent weak signals should exceed either alone, but never certainty (global cap < 1.0). The calculus exists so confidence is a defined function of evidence, not a hand-tuned verdict.

---

## Slide 11 — Candidate Selection: Resolve, Refuse, or Abstain

- **Goal:** Define the three-way decision and the margin logic.
- **Main message:** A confident, clear winner resolves; near-ties abstain on purpose; nothing credible ⇒ unresolved.
- **Suggested diagram:** Decision gate:
  ```
                 top candidate conf ≥ 0.50 ?
                    /no                 \yes
              UNRESOLVED         (top − second) ≥ margin(0.15)?
              (low confidence)     /no                 \yes
                              AMBIGUOUS             RESOLVED
                            (retain competitors)   (chosen + trail)
  ```
- **Bullets:**
  - RESOLVED: one candidate above floor and clear of the runner-up
  - AMBIGUOUS: multiple credible candidates within the margin → **no choice made**
  - UNRESOLVED: no candidate clears the floor
- **Speaker notes:** The deliberate-abstention point: a wrong resolution silently corrupts every downstream stage, so when evidence is genuinely split the correct engineering answer is to refuse and hand the conflict to a human/F6. AMBIGUOUS is a feature, not a failure. Competitors and the margin are retained so the caller can see *why* it abstained.

---

## Slide 12 — Diagnostics: A Taxonomy of "Why Not"

- **Goal:** Show unresolved outcomes are structured, actionable diagnoses.
- **Main message:** An unresolved action names *which analysis boundary it hit*, not "failed".
- **Suggested diagram:** Reason tree grouped by cause-class:
  ```
  UNRESOLVED
  ├─ missing evidence      : NO_EVIDENCE
  ├─ below threshold       : LOW_CONFIDENCE
  ├─ analysis limitation   : REGISTRAR_STORE_NOT_REACHED, EXTERNAL_DEFINITION,
  │                          MISSING_POINTSTO, REGISTRATION_OUT_OF_TU
  └─ unsupported pattern    : REGISTRAR_SEARCH_THEN_WRITE, DYNAMIC_ACTION_ID
  ```
- **Bullets:**
  - Reasons distinguish "no signal" from "signal we intentionally don't follow"
  - Specializations exist (e.g. search-then-write ⊂ store-not-reached) for actionability
  - These are *scope statements*, not bugs
- **Speaker notes:** Use the registrar example: "store not reached" is generic; "search-then-write" specifically names a loop+predicate slot search that the baseline does not model. That precision lets a reader decide whether to extend the analyzer or accept the gap. Diagnostics feed evaluation-run summaries.

---

## Slide 13 — Worked Example (the detailed slide)

- **Goal:** End-to-end trace on one concrete case, plus the ambiguity contrast.
- **Main message:** Watch source become evidence become a scored, auditable resolution.
- **Suggested diagram:** Vertical pipeline with a side branch:
  ```
  SOURCE
    static Reg t[] = { { ACTION_DATA_TRANSFER, foo } };     // registration
    switch (f->action){ case ACTION_DATA_TRANSFER: bar(); } // dispatch (side branch)
        │
        ▼ extractors
  Evidence A: kind=REGISTRATION_INIT, cb=foo, id=ACTION_DATA_TRANSFER (EXACT), site=reg
  Evidence B: kind=ENUM_CASE,        cb=bar, id=ACTION_DATA_TRANSFER (EXACT), site=switch
        │
        ▼ calculus
  candidate foo: 0.80   |   candidate bar: ~0.85(weak-capped)   ← two DIFFERENT callbacks
        │
        ▼ selection
  margin small + different callbacks → AMBIGUOUS (retain foo & bar + conflict)
  ---------------------------------------------------------------
  Remove the switch → only Evidence A → foo 0.80 ≥ floor, no rival → RESOLVED → foo
  ```
- **Bullets:**
  - Two independent extractors fire on the same action id, different callbacks
  - Calculus scores each; selection detects the conflict and abstains
  - Drop the competitor and the same machinery cleanly resolves
- **Speaker notes:** This is the money slide — spend time. Show that the *same* pipeline yields AMBIGUOUS or RESOLVED purely from evidence, no special-casing. Point out the evidence trail on the resolved path (table entry → handler ref, with file/line). If asked, note the corroboration variant: two evidences for the *same* callback would noisy-OR *up*, not conflict.

---

## Slide 14 — Output Schema

- **Goal:** Define the contract handed downstream.
- **Main message:** One authoritative per-action result set, plus a resolved-only convenience view, all evidence-linked.
- **Suggested diagram:** Nested output shape:
  ```
  result
  ├─ handler_resolutions[]        ← authoritative, one per action
  │    ├─ status (RESOLVED/AMBIGUOUS/UNRESOLVED)
  │    ├─ chosen                  (only if RESOLVED)
  │    ├─ candidates[] { fn, confidence, evidence_kinds, evidence[] { records[] } }
  │    ├─ conflict  { competitors, margin }   (AMBIGUOUS)
  │    └─ unresolved{ reason, attempted }     (UNRESOLVED)
  ├─ handler_maps[]               ← resolved-only, back-compat
  └─ limitations[]                ← global scope caveats
  ```
- **Bullets:**
  - `handler_resolutions` is the source of truth; `handler_maps` is a resolved-only subset
  - Every candidate carries its evidence and record trail
  - Conflict / unresolved reports make non-resolution first-class
- **Speaker notes:** Explain the two-view design: legacy consumers want "just the resolved map"; auditors and F6 want the full outcome including why-not. Confidence on a resolution's map entry reflects the *selected* evidence, distinct from the aggregated candidate score — flag this so no one conflates them.

---

## Slide 15 — Downstream Consumption

- **Goal:** Show how the resolution unlocks the rest of the pipeline.
- **Main message:** The resolved handler is the anchor from which taint sources, sinks, and checks are all located.
- **Suggested diagram:** Anchor-expansion chain:
  ```
  resolved handler(action)
        ↓  entry params = untrusted payload
  protocol field binding      (which field → which variable)
        ↓
  source identification       (taint roots inside the handler)
        ↓
  sink reachability           (does tainted data reach a dangerous API?)
        ↓
  expected-check matching     (are spec-required validations present?)
        ↓
  security finding candidate  (F6)
  ```
- **Bullets:**
  - Handler = the function where payload enters program semantics
  - Field binding and sink search are scoped by the handler
  - A missing/ambiguous resolution ⇒ downstream either narrows scope or defers
- **Speaker notes:** Make the dependency vivid: no handler ⇒ no source root ⇒ no taint ⇒ no finding for that action. This is why F2-A's abstention discipline matters — a confident-but-wrong handler would send the taint analysis into the wrong function and manufacture false results.

---

## Slide 16 — Current Scope

- **Goal:** State precisely what is in the baseline.
- **Main message:** The baseline covers the structural, statically-decidable registration forms and handles ambiguity explicitly.
- **Suggested diagram:** Checklist panel:
  ```
  ✓ aggregate initialization        ✓ designated initialization
  ✓ indexed / correlated field store ✓ registrar tracing (reaches store)
  ✓ delegated registrar (depth 2)    ✓ symbolic receiver correlation (shared slot)
  ✓ ambiguity detection & abstention ✓ structured diagnostics
  ```
- **Bullets:**
  - Everything here is AST + symbol resolution + bounded call following
  - Ambiguity and non-resolution are supported *outcomes*, not gaps
  - Scope is defined by decidability without heavy semantic reasoning
- **Speaker notes:** Draw the line explicitly: the baseline is what can be recovered soundly from structure and identifiers, plus shallow call following. Anything requiring value reasoning is deferred (next slide). This boundary is a design choice favoring precision and explainability.

---

## Slide 17 — Limitations (Intentional Exclusions)

- **Goal:** Be candid about what the baseline will not do and why.
- **Main message:** The excluded patterns all require value/loop/alias reasoning whose cost and unsoundness risk exceed the baseline's precision budget.
- **Suggested diagram:** Excluded set with the capability each would need:
  ```
  search-then-write registrar   → loop + predicate reasoning
  runtime slot selection        → symbolic index resolution
  alias-to-slot binding         → alias / points-to analysis
  cross-procedure slot rebuild  → interprocedural value flow
  general dynamic action ids    → DFG-based escalation
  ```
- **Bullets:**
  - Each is *detected and named*, not silently mishandled
  - Excluded because they trade precision/soundness for coverage
  - They form a concrete, prioritizable escalation backlog
- **Speaker notes:** Tie back to diagnostics: when the baseline meets one of these, it emits the matching reason and abstains. Argue the engineering position: a precise, explainable core plus honest gaps beats a broad, opaque heuristic that downstream cannot trust. These are candidate future work, gated on evaluation showing they matter in real firmware.

---

## Slide 18 — Evaluation & Conclusions

- **Goal:** Validate the approach and close with the thesis.
- **Main message:** Behavior is pinned by capability + regression tests over synthetic patterns; the evidence-based design is what makes results trustworthy and extensible.
- **Suggested diagram:** Validation matrix + closing arrow:
  ```
  synthetic fixtures ─┬─ supported forms   → expected RESOLVED (kind, confidence)
                      ├─ ambiguous forms   → expected AMBIGUOUS (retain, margin)
                      └─ unsupported forms → expected UNRESOLVED (named reason)
        regression tests lock each behavior (incl. positional-unchanged guards)
                              │
                              ▼
     evidence-based resolution  ⇒  auditable · corroborating · honest about limits
  ```
- **Bullets:**
  - Each registration mechanism has a fixture asserting exact expected outcome
  - Negative & unsupported cases assert *the right refusal*, not just "no crash"
  - Conclusion: evidence + calculus > heuristic matching; it enables protocol-aware F6 analysis and has a clear extension path (escalation extractors feeding the same evidence bus)
- **Speaker notes:** Explain the test philosophy: capability tests prove a mechanism works; regression tests prevent silent drift; unsupported-pattern tests assert the diagnosis. Close on the thesis: because every resolution is a scored function of traceable evidence with an explicit abstain path, downstream security reasoning can rely on it — and new extractors extend coverage without touching the calculus or the decision logic. End by inviting the hard questions (confidence tuning, soundness of noisy-OR, depth bound choice).

---

### Appendix (hold-slides for Q&A, not presented)

- **A1 — Calculus parameters:** priors per kind, match-strength multipliers, weak-only cap, global cap, acceptance floor, ambiguity margin, conflict penalty, registrar depth. Present as a table if pressed.
- **A2 — Match-strength ladder:** exact identifier ▷ normalized identifier ▷ heuristic substring ▷ name-only ▷ none — with what each is trusted for.
- **A3 — Provenance grouping:** why within-group max and cross-group noisy-OR; the double-counting failure it prevents.
- **A4 — Designated-vs-positional AST:** the lowering difference (wrapped member assignments) that made them structurally distinct despite identical semantics.
```
