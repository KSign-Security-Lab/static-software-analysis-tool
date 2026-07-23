# F2-A · Handler Resolution — Technical Design Review

**Format:** research-conference technical review · 20 slides
**Audience:** engineers & security researchers fluent in static analysis, AST/CPG, protocol analysis
**Style rules:** one idea per slide · minimal text · boxes-and-arrows over prose · diagrams must be technically accurate · assume adversarial Q&A

> Framing note carried through the whole deck: F2-A produces **evidence-backed candidates**, not confirmed facts. It resolves *which source function handles a protocol action*; it never claims a vulnerability. Every claim is traceable to a file/line record. Keep this honesty visible on every slide that states a result.

> **Architectural backbone (recurring rail):** the whole subsystem is four layers, each producing only inputs for the next —
> **Recognition → Evidence → Calculus → Decision.** Slides 9–13 carry a rail showing which layer is active. No layer decides above its station: extractors recognize, they never resolve.

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
- **Speaker notes:** State the one-sentence thesis and the honesty contract up front. Everything downstream trusts F2-A's mapping, so F2-A must either be right or *say it doesn't know*. Preview that the talk's spine is the four-layer backbone: recognition → evidence → calculus → decision.

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
                    ▲ binding is latent in data, not control flow
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
- **Suggested diagram:** Call graph with the critical edge missing (render the missing edge dashed/red):
  ```
  dispatch(frame) ‑‑calls‑‑▶ (*table[i].fn)()   ⟵ indirect: NO static edge to remote_handler
  registration:  table[k] = { ACTION, remote_handler }   ⟵ the edge lives HERE, in data
  ```
- **Bullets:**
  - Dynamic dispatch ⇒ the caller→handler edge is absent from the CG
  - The real binding is expressed in *data* (registration sites), not control flow
  - So we must recover the edge from **registration structure + identifier matching**, not from calls
- **Speaker notes:** This is the crux — let it breathe. A naive call-graph walk fails by construction. The binding is latent in initializer tables, assignments, and registrar calls. F2-A's job is to reconstruct that latent edge statically. Anticipate: "why not just run it?" — static, pre-deployment, whole-firmware, no harness.

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
- **Speaker notes:** The KB is the ground truth of "what identifiers denote which action". The AST supplies the *shape* of registration; symbols tell us a reference is a real internal function, not an external stub. How those identifiers actually get matched is the next slide.

---

## Slide 6 — Protocol Identifier Normalization

- **Goal:** Explain the KB's real job — turning one protocol action's many code spellings into a single canonical identity that extractors can match against.
- **Main message:** A protocol action has one meaning but many representations; the KB normalizes them into one canonical **ActionIdentifier**, and match strength falls directly out of *how* a code token corresponds to it.
- **Suggested diagram (the centerpiece — two symmetric sides meeting at a comparison, not a list):**
  ```
        KB SIDE                                        CODE SIDE
   "RemoteStartTransaction"  (wire string)      raw identifier found in source
            │                                             │
            ▼                                             ▼
   ╔════════════════════╗                        ┌────────────────────┐
   ║ canonical           ║                        │ ActionIdentifier    │
   ║ Action Identity     ║                        │ extracted from code │
   ╚════════════════════╝                        └────────────────────┘
    subsumes many spellings:                              │
    macro · enum · numeric id · aliases                   │
            │                                             │
            └──────────────── compare  ⇔ ─────────────────┘
                                   │
                 match strength = exactness of correspondence
      EXACT_IDENTIFIER ▷ NORMALIZED ▷ HEURISTIC_SUBSTRING ▷ NAME_ONLY
  ```
- **Bullets:**
  - The KB provides the semantic identity that unifies multiple syntactic representations
  - Extractors don't compare strings ad hoc — they compare a raw id against the canonical identity
  - The match-strength ladder is not a tuning knob; it is *which representation matched, how exactly*
- **Speaker notes:** This is the conceptual hinge between the protocol world and the code world. Walk the ladder: a macro/enum symbol hit or numeric-id hit is EXACT; a normalized-name hit is NORMALIZED; a substring/token overlap is HEURISTIC_SUBSTRING; a function-name resemblance with no id is NAME_ONLY. Everything the calculus later does with "match strength" is grounded here. Note it's bidirectional: KB produces the canonical identity, the code site produces a raw identifier, and matching scores their correspondence.

---

## Slide 7 — Registration Mechanisms: A Taxonomy

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

## Slide 8 — Why Multiple Extractors, Not One Matcher

- **Goal:** Defend the multi-extractor architecture *and* introduce the four-layer backbone.
- **Main message:** Extractors *recognize*; they never *decide*. Recognition feeds a uniform evidence stream, and everything downstream is a separate layer.
- **Suggested diagram (introduce the backbone here — this is the deck's spine):**
  ```
  [aggregate][designated][indexed][correlated][registrar][delegated][name]
       \        \        |        /        /        /       /
        ▼        ▼       ▼       ▼        ▼        ▼       ▼
   ┌────────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
   │ RECOGNITION│──▶│ EVIDENCE │──▶│  CALCULUS │──▶│ DECISION │
   └────────────┘   └──────────┘   └───────────┘   └──────────┘
    recognizers      typed records   scoring +       resolve /
    (this slide)     w/ provenance   combination     abstain
        "no layer decides above its station"
  ```
- **Bullets:**
  - Different mechanisms correlate id↔callback differently (same node / sibling field / shared slot / arg→param)
  - Independent extractors ⇒ independent evidence ⇒ *corroboration* is possible
  - A miss in one extractor is a precise diagnostic, not a silent whole-system failure
- **Speaker notes:** Land the backbone explicitly and promise the audience the next five slides walk it left to right: Recognition (extractors) → Evidence (the record) → Calculus (scoring, then combination) → Decision (resolve/abstain). This is the mental model to hold for the rest of the talk. Extractors are recognizers, not deciders — that single constraint is what makes corroboration and honest abstention possible.

---

## Slide 9 — Recognition Layer: Extractor Capabilities

- **Goal:** One-glance capability table; pattern / evidence / strength / limit per extractor, split by role.
- **Main message:** Recognition splits into *structural* extractors (high-trust, id+callback present) and *corroborative* signals (low-trust, usable only to reinforce).
- **Rail:** `[ ●Recognition › Evidence › Calculus › Decision ]`
- **Suggested diagram (two visually distinct bands, not one flat table):**
  ```
  ── STRUCTURAL (high prior) ─────────────────────────────────────────
   Extractor        Recognizes                 Emits              Boundary
   aggregate init   { ID, fn }                 REGISTRATION_INIT  inline id only
   designated init  { .a=ID, .fn=fn }          REGISTRATION_INIT  same struct init
   indexed / field  h[ID]=fn ; t[k].*=…        REGISTRATION_ASSIGN shared slot key
   registrar call   f(ID, fn) → stores fn      REGISTRAR_CALL     must reach store
   delegated        f→g→ store (arg→param)     REGISTRAR_CALL     depth-bounded

  ── CORROBORATIVE (low prior) ───────────────────────────────────────
   dispatch site    switch(id) → handler       ENUM_CASE          weak alone
   name similarity  fn name ≈ action           NAME_MATCH         weak alone
  ```
- **Bullets:**
  - Structural extractors carry high prior weight; they alone can resolve
  - Corroborative signals cannot resolve on their own — they only reinforce
  - Every extractor's boundary is a named limitation, surfaced downstream
- **Speaker notes:** Walk one structural row (designated): correlation is "same enclosing initializer, order-independent, no field-name guessing". Contrast registrar: it must follow the call into the callee and reach the terminal store, else it emits nothing and reports the miss. The structural/corroborative divide is what the calculus later encodes as prior weight and the weak-only cap.

---

## Slide 10 — The Evidence Model

- **Goal:** Define the currency of the system.
- **Main message:** Extractors speak one language: a structured evidence record with provenance and a source trail.
- **Rail:** `[ Recognition › ●Evidence › Calculus › Decision ]`
- **Suggested diagram (a conceptual schema *card*, not a struct):**
  ```
  ╔══════════════════ EVIDENCE (record) ══════════════════╗
  ║  field           meaning                                ║
  ║ ───────────────  ────────────────────────────────────  ║
  ║  action id       matched identifier  (+ match strength) ║
  ║  callback        the resolved internal function         ║
  ║  kind            which mechanism produced it             ║
  ║  provenance      site / group key (dedup + grouping)    ║
  ║  confidence      Prior(kind) shaped by match strength    ║
  ║  dispatch site   where the binding is observed          ║
  ║  records[]       ordered file/line trail (auditable)    ║
  ╚═════════════════════════════════════════════════════════╝
  ```
- **Bullets:**
  - Evidence is *typed by mechanism* and *scored by match quality*
  - Provenance key makes duplicates and same-site evidence identifiable
  - Records preserve the original source expressions and locations
- **Speaker notes:** The record trail is not decoration — it is what makes a resolution reviewable by a human who did not run the tool. Multiple extractors emit simultaneously because they observe independent facts about the same binding. This record is the boundary object between Recognition and Calculus: extractors fill it, the calculus consumes it.

---

## Slide 11 — Evidence Scoring

- **Goal:** Show how a *single* piece of evidence gets a score — before any merging.
- **Main message:** One evidence's score is its kind's prior, shaped by how exactly its identifier matched.
- **Rail:** `[ Recognition › Evidence › ●Calculus › Decision ]`
- **Suggested diagram:**
  ```
  one piece of evidence
     Prior(kind)      ──┐   structural kind  → high prior
                         ├─▶  evidence score = Prior(kind) shaped by Match Strength
     Match Strength   ──┘   exact ↦ preserved  ·  heuristic ↦ discounted
                                              ·  name-only ↦ weak
  ```
- **Bullets:**
  - **Prior(kind)** — structural mechanisms outrank dispatch/name signals
  - **Match Strength** — exact identifier preserved; weaker correspondences discounted
  - Output: a per-evidence score; no candidate merging happens yet
- **Speaker notes:** Keep this slide strictly about *one* evidence. Give the intuition: a structural registration with an exact symbol match scores near its full prior; the same mechanism with only a substring match is discounted; a name-only signal stays weak regardless. (Concrete priors and multipliers live in Appendix A1 — don't put numbers on the slide.) This is deliberately the simpler half of the calculus; combination is next.

---

## Slide 12 — Evidence Combination

- **Goal:** Explain how many scored evidences become one confidence per candidate — and *why* we combine at all.
- **Main message:** Two ordered steps: first *collapse* duplicate evidence within a site (MAX), then *combine* the surviving independent sites (noisy-OR) — corroboration is counted only after duplicates are gone. Caps and a conflict penalty follow.
- **Rail:** `[ Recognition › Evidence › ●Calculus › Decision ]`
- **Suggested diagram (a two-step order, collapse → combine):**
  ```
  many scored evidences for one candidate
        │
   step 1 · COLLAPSE   group by provenance → within a site : MAX
        │              (same site ≠ new information; duplicates removed)
        ▼
   step 2 · COMBINE    across independent sites : noisy-OR
        │              (independent corroboration ↑ belief)
        ▼
                       Weak-only Cap · Global Cap · Conflict Penalty
        ▼
             candidate confidence
  ```
- **Bullets:**
  - **Step 1 — collapse:** same-site duplicates reduce to their MAX, so one site can't inflate itself
  - **Step 2 — combine:** only then do *independent* sites corroborate (noisy-OR) — two weak-but-independent signals beat either alone
  - Finally: weak-only evidence is capped; competing candidates incur a conflict penalty
- **Speaker notes:** This is the intellectual core — spend time. Why noisy-OR: independent corroboration should raise belief but never reach certainty (a Global Cap keeps confidence below 1.0). Why within-site MAX: two records from the *same* registration are not two witnesses. The Weak-only Cap prevents a pile of name/dispatch hints from masquerading as strong evidence. (Numeric caps, margins, penalty factors → Appendix A1.)

---

## Slide 13 — Candidate Selection: Resolve, Refuse, or Abstain

- **Goal:** Define the three-way decision and the margin logic.
- **Main message:** A confident, clear winner resolves; near-ties abstain on purpose; nothing credible ⇒ unresolved.
- **Rail:** `[ Recognition › Evidence › Calculus › ●Decision ]`
- **Suggested diagram:** Decision gate (symbolic thresholds):
  ```
                 top candidate ≥ Acceptance Floor ?
                    /no                 \yes
              UNRESOLVED         (top − second) ≥ Ambiguity Margin ?
              (low confidence)     /no                 \yes
                              AMBIGUOUS             RESOLVED
                            (retain competitors)   (chosen + trail)
  ```
- **Bullets:**
  - RESOLVED: one candidate above the **Acceptance Floor** and clear of the runner-up
  - AMBIGUOUS: multiple credible candidates within the **Ambiguity Margin** → **no choice made**
  - UNRESOLVED: no candidate clears the floor
- **Speaker notes:** The deliberate-abstention point — the most interesting design stance, so dwell here. A wrong resolution silently corrupts every downstream stage, so when evidence is genuinely split the correct engineering answer is to refuse and hand the conflict to F6/a human. AMBIGUOUS is a feature, not a failure. Competitors and the margin are retained so the caller can see *why* it abstained. (Floor and margin values → Appendix A1.)

---

## Slide 14 — Diagnostics: A Taxonomy of "Why Not"

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

## Slide 15 — Worked Example (the detailed slide)

- **Goal:** End-to-end trace on one concrete case, plus the ambiguity contrast.
- **Main message:** Watch source become evidence become a scored, auditable resolution — the backbone in motion.
- **Suggested diagram:** Vertical pipeline showing all four stages, Evidence explicit as its own intermediate layer (concrete scores are illustrative and stay here):
  ```
  SOURCE
    static Reg t[] = { { ACTION_DATA_TRANSFER, foo } };     // registration
    switch (f->action){ case ACTION_DATA_TRANSFER: bar(); } // dispatch (side branch)
        │
        ▼ RECOGNITION (extractors recognize two registration shapes)
        │
        ▼ EVIDENCE (typed records — the intermediate abstraction)
  Evidence A: kind=REGISTRATION_INIT, cb=foo, id=ACTION_DATA_TRANSFER (EXACT), site=reg
  Evidence B: kind=ENUM_CASE,        cb=bar, id=ACTION_DATA_TRANSFER (EXACT), site=switch
        │
        ▼ CALCULUS (score each evidence → collapse → combine per candidate)
  candidate foo: 0.80   |   candidate bar: 0.85 (weak-capped)   ← two DIFFERENT callbacks
        │
        ▼ DECISION
  margin small + different callbacks → AMBIGUOUS (retain foo & bar + conflict)
  ---------------------------------------------------------------
  Remove the switch → only Evidence A → foo clears floor, no rival → RESOLVED → foo
  ```
- **Bullets:**
  - Two independent extractors fire on the same action id, different callbacks
  - Scoring then combination rank each; the decision layer detects the conflict and abstains
  - Drop the competitor and the same machinery cleanly resolves
- **Speaker notes:** The money slide — spend the most time. Show that the *same* four layers yield AMBIGUOUS or RESOLVED purely from evidence, no special-casing. Numbers are kept here only because they make the trace legible. Point out the evidence trail on the resolved path (table entry → handler ref, with file/line). If asked, the corroboration variant: two evidences for the *same* callback would noisy-OR *up*, not conflict.

---

## Slide 16 — Output Schema

- **Goal:** Define the contract handed downstream.
- **Main message:** One authoritative per-action result set, plus a resolved-only convenience view, all evidence-linked.
- **Suggested diagram (architectural schema — layered blocks, not JSON):**
  ```
  ┌──────────────────────── F2-A RESULT ────────────────────────┐
  │                                                              │
  │  handler_resolutions   ── authoritative · one per action     │
  │     • status            RESOLVED / AMBIGUOUS / UNRESOLVED     │
  │     • chosen            present only when RESOLVED           │
  │     • candidates        each carries its evidence + records  │
  │     • conflict          competitors + margin  (AMBIGUOUS)    │
  │     • unresolved        reason + attempts     (UNRESOLVED)   │
  │                                                              │
  │  handler_maps          ── resolved-only view · back-compat    │
  │  limitations           ── global scope caveats                │
  └──────────────────────────────────────────────────────────────┘
  ```
- **Bullets:**
  - `handler_resolutions` is the source of truth; `handler_maps` is a resolved-only subset
  - Every candidate carries its evidence and record trail
  - Conflict / unresolved reports make non-resolution first-class
- **Speaker notes:** Explain the two-view design: legacy consumers want "just the resolved map"; auditors and F6 want the full outcome including why-not. Confidence on a resolution's map entry reflects the *selected* evidence, distinct from the aggregated candidate score — flag this so no one conflates them.

---

## Slide 17 — Downstream Consumption

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

## Slide 18 — Current Scope

- **Goal:** State precisely what is in the baseline.
- **Main message:** The baseline covers the structural, statically-decidable registration forms and handles ambiguity explicitly.
- **Suggested diagram:** Checklist panel:
  ```
  ✓ aggregate initialization        ✓ designated initialization
  ✓ indexed / correlated field store ✓ registrar tracing (reaches store)
  ✓ delegated registrar (bounded)    ✓ symbolic receiver correlation (shared slot)
  ✓ ambiguity detection & abstention ✓ structured diagnostics
  ```
- **Bullets:**
  - Everything here is AST + symbol resolution + bounded call following
  - Ambiguity and non-resolution are supported *outcomes*, not gaps
  - Scope is defined by decidability without heavy semantic reasoning
- **Speaker notes:** Draw the line explicitly: the baseline is what can be recovered soundly from structure and identifiers, plus shallow call following. Anything requiring value reasoning is deferred (next slide). This boundary is a design choice favoring precision and explainability.

---

## Slide 19 — Limitations (Intentional Exclusions)

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

## Slide 20 — Evaluation & Conclusions

- **Goal:** Validate the approach and close with the thesis.
- **Main message:** Behavior is pinned by capability + regression tests over synthetic patterns; the evidence-based design is what makes results trustworthy and extensible.
- **Suggested diagram:** Validation matrix, then the architectural backbone as the final image on screen:
  ```
  synthetic fixtures ─┬─ supported forms   → expected RESOLVED (kind, confidence)
                      ├─ ambiguous forms   → expected AMBIGUOUS (retain, margin)
                      └─ unsupported forms → expected UNRESOLVED (named reason)
        regression tests lock each behavior (incl. positional-unchanged guards)

  ── final takeaway ────────────────────────────────────────────────
     Recognition ─▶ Evidence ─▶ Calculus ─▶ Decision

     "By separating recognition from decision through an evidence
      abstraction, F2-A becomes conservative, auditable, and
      naturally extensible."
  ```
- **Bullets:**
  - Each registration mechanism has a fixture asserting exact expected outcome
  - Negative & unsupported cases assert *the right refusal*, not just "no crash"
  - Final message: the backbone itself — **Recognition → Evidence → Calculus → Decision** — is the contribution
- **Speaker notes:** Explain the test philosophy first: capability tests prove a mechanism works; regression tests prevent silent drift; unsupported-pattern tests assert the diagnosis. Then close on the architecture, not the tests — leave the backbone on screen and deliver the takeaway verbatim: *"By separating recognition from decision through an evidence abstraction, F2-A becomes conservative, auditable, and naturally extensible."* Conservative because it abstains rather than guess; auditable because every resolution traces to evidence records; extensible because new extractors feed the same evidence bus without touching the calculus or the decision logic. End by inviting the hard questions.

---

### Appendix (hold-slides for Q&A, not presented)

- **A1 — Calculus parameters:** priors per kind, match-strength multipliers, weak-only cap, global cap, acceptance floor, ambiguity margin, conflict penalty, registrar depth bound. Present as a table if pressed. *(This is the sole home for concrete numeric values.)*
- **A2 — Provenance grouping:** why within-group MAX and cross-group noisy-OR; the double-counting failure it prevents.
- **A3 — Designated-vs-positional AST:** the lowering difference (wrapped member assignments) that made them structurally distinct despite identical semantics.

> Note: the match-strength ladder and identifier normalization are now core material (Slide 6), not an appendix hold-slide — they are part of the architecture, not a Q&A detail.
