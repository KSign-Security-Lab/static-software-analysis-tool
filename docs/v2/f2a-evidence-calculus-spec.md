# F2-A Evidence Calculus — Phase 2 policy spec

**Status: REVIEWED & IMPLEMENTED** — `select_corroborate` is the default policy;
`select_cascade` remains selectable (`F2AAnalyzer(selection="cascade")`). The
calculus below is the implemented behavior. Review decisions applied:

- WEAK_ONLY_CAP = 0.85 (configurable via `CalculusConfig`).
- CONFLICTING penalty = cap M at 0.70 then ×0.5; pre/post scores exposed on
  `ResolutionEvidence.score_pre_penalty` / `.score`.
- Strong-competitor ambiguity hardening: **not adopted** (hook kept as
  `CalculusConfig.strong_competitor_hardening=False`).
- Below `MIN_CONFIDENCE` → UNRESOLVED(LOW_CONFIDENCE), candidates retained.
- Duplicate registrations in one table share one `("site", table)` group → max,
  no corroboration.
- Weak provenance key = global `("token", normalized_name)` collapse (conservative).
- Dedup survivor uses an explicit `MATCH_STRENGTH_RANK` table (tested directly).

Prereqs shipped: `ActionIdentifier`, `ResolutionEvidence` (with `provenance_group`),
`HandlerCandidate`, `select_cascade`, and the public `HandlerResolution` projection.

---

## Locked constants

Kind weight `W(kind)` (priors == historical strategy confidences):

| kind | W |
|---|---|
| STRING_DISPATCH | 0.90 |
| ENUM_CASE | 0.85 |
| REGISTRATION_INIT / REGISTRATION_ASSIGN | 0.80 |
| REGISTRAR_CALL | 0.70 |
| NAME_MATCH (pattern) | 0.70 |
| NAME_MATCH (token) | 0.65 |
| DISPATCH_SITE | 0.00 |

Match-strength multiplier `M(match_strength)` (uses the Q3 granularity):

| match_strength | M |
|---|---|
| EXACT_IDENTIFIER | 1.00 |
| RESOLVED_VALUE | 0.95 |
| NORMALIZED_NAME | 0.85 |
| HEURISTIC_SUBSTRING | 0.70 |
| NONE | 0.00 |

Policy scalars: `MIN_CONFIDENCE = 0.50`, `AMBIGUITY_MARGIN = 0.15`,
`GLOBAL_CAP = 0.99`, `WEAK_ONLY_CAP = 0.85`.

"**Strong basis**" ≡ match_strength ∈ {EXACT_IDENTIFIER, RESOLVED_VALUE}.
"**Weak basis**" ≡ match_strength ∈ {NORMALIZED_NAME, HEURISTIC_SUBSTRING}.

---

## 1. Exact evidence identity (deduplication)

Collapse observations that are literally the same signal, so overlapping
extractors don't count one fact twice. Distinct from provenance grouping (§2).

**Dedup key:**

```
(kind, callback, dispatch_site_or(-1), tuple(sorted(nodes)))
```

- **Missing `dispatch_site`** → normalized to the sentinel `-1` (never blocks
  dedup; two site-less evidences with equal (kind, callback, nodes) still collapse).
- **Missing / empty `nodes`** → `nodes_key = ()`. Identity then rests on
  (kind, callback, site); acceptable because those anchor the observation.
- **Extractor identity does NOT participate.** Two different extractors emitting
  structurally identical evidence ARE duplicates and must collapse — that is the
  "same registration seen by two extractors" case.

**Deterministic survivor when duplicates differ only in metadata**
(`match_strength`, `mapping_evidence`, `extractor`, `provenance_group`, `score`):
keep the one with, in order, (1) highest `match_strength` rank, (2) highest
`score`, (3) lexicographically smallest `extractor`. Deterministic and never
discards the strongest representation.

Dedup runs at candidate construction, before grouping.

---

## 2. Provenance groups (computable key)

Independence unit for aggregation: evidence in one group is the *same underlying
signal* (do not double-count); different groups are independent (may corroborate).

**Computable key:**

```
provenance_group(e) =
    ("token", e.action_id.normalized_name)          if e is WEAK basis
    ("site",  site_key(e))                           if e is STRONG basis
```

`site_key(e)` by kind (the code artifact the strong match is anchored to):

| kind | site_key |
|---|---|
| REGISTRATION_INIT | enclosing table (initialized LOCAL / top-level `arrayInitializer` node) |
| REGISTRATION_ASSIGN | assigned base symbol (`g_handlers` in `g_handlers[id]=fn`) |
| ENUM_CASE | enclosing `switch` node (else the dispatch method) |
| STRING_DISPATCH | dispatcher method + branch control-structure |
| REGISTRAR_CALL | the registrar call node |

**Why this resolves the hard cases:**

- **ENUM_CASE + NAME_MATCH on a shared normalized token** (e.g.
  `data_transfer_enum`: case `ACTION_DATA_TRANSFER` matched via UPPER_SNAKE, and
  `handle_data_transfer` via name pattern — both *weak basis*): both map to
  `("token", "DataTransfer")` → **same group** → they do **not** corroborate.
  A coincidence of spelling cannot inflate confidence.
- **Enum matched a real KB symbol** (strong) **+ a name match** (weak): enum →
  `("site", switch)`, name → `("token", X)` → **different groups** → they
  corroborate (a declared symbol and the naming convention are genuinely
  independent signals).
- **Duplicate registrations in one table** (`{MSG_SET_PROFILE,h}`, `{41,h}`, both
  strong, same array): both → `("site", g_table)` → **same group** → max, no
  inflation.
- **Registrations in two different tables** for one callback → different
  `site_key` → independent → corroborate.
- **Evidence sharing CPG nodes** is already collapsed by §1 dedup; near-duplicates
  (same site, different nodes) land in the same `("site", …)` group → max.

---

## 3. Aggregation

Per candidate (all evidence points to one callback):

1. **Per-evidence base score** `s_e = W(kind) × M(match_strength)`.
2. **Identifier-consistency penalty (per evidence, applied FIRST — see §5):**
   if `action_id.consistency == CONFLICTING`, set `M := min(M, 0.70)` (cap at
   HEURISTIC) then `s_e := s_e × 0.5`. PARTIAL / CONSISTENT: unchanged.
3. **Max within provenance group:** `g = max(s_e for e in group)`.
4. **Noisy-OR across groups:** `raw = 1 − Π_g (1 − g)`.
5. **Caps:** `confidence = min(GLOBAL_CAP, raw)`, and additionally
   `confidence = min(confidence, WEAK_ONLY_CAP)` if the candidate has **no**
   strong-basis group. (Weak/name-only evidence can never reach near-certainty,
   even across multiple weak groups.)

Ordering of operations is fixed: **penalties (per-evidence) → group-max →
noisy-OR → caps.** Penalties are pre-aggregation so a conflicted identifier is
demoted before it can corroborate anything.

---

## 4. Contradiction and ambiguity

Candidates are grouped by callback; two candidates with different callbacks are
**competitors**.

- `margin = c1.confidence − c2.confidence` over the post-aggregation ranking
  (c1 = top, c2 = runner-up).
- A `ConflictReport` is emitted whenever ≥ 2 candidates exist — even when RESOLVED
  — so contradiction is always visible.

**Status decision:**

```
0 candidates                                   -> UNRESOLVED  (reason from _diagnose_unresolved; default NO_EVIDENCE)
c1.confidence < MIN_CONFIDENCE                  -> UNRESOLVED  (reason LOW_CONFIDENCE)      [new reason]
>=2 candidates and margin < AMBIGUITY_MARGIN    -> AMBIGUOUS   (chosen = None, conflict set)
otherwise                                       -> RESOLVED    (chosen = c1; conflict set if >=2 candidates)
```

- **Tie** (`margin == 0`, incl. exact ties) → AMBIGUOUS. Public candidate order is
  still deterministic (selection order: chosen-first when RESOLVED, else confidence
  desc then function/file/line).
- **Minimum confidence:** a sole candidate below `MIN_CONFIDENCE` is UNRESOLVED
  (`LOW_CONFIDENCE`), *not* RESOLVED-flagged-low. This is a deliberate Phase-2
  change from Phase-1's resolve-low behavior.
- Optional hardening (not adopted unless review wants it): force AMBIGUOUS when the
  top two candidates each own a strong-basis group and `margin < 2×AMBIGUITY_MARGIN`.
  Default relies on the single margin rule.

---

## 5. `ActionIdentifier.consistency()` in the calculus

- **CONFLICTING** → per-evidence penalty (§3.2): cap `M` at 0.70 then halve `s_e`.
  Example: an EXACT registration `0.80×1.0=0.80` with a conflicting identifier →
  `0.80×0.70=0.56 → ×0.5 = 0.28`. Retained (F6 keeps provenance), heavily demoted.
- **PARTIAL vs CONSISTENT:** both are **score-neutral** (no penalty, no bonus).
  They differ only diagnostically: CONSISTENT means ≥ 2 independent identifier
  fields agree; PARTIAL means < 2 cross-checkable fields (nothing to corroborate).
  Consistency never *raises* score — it only ever penalizes on conflict — so it
  cannot inflate confidence.
- **Public diagnostics:** `HandlerResolutionCandidate.action_id_consistency`
  (CONSISTENT | CONFLICTING | PARTIAL) already exists; add
  `identifier_conflict: bool` (true if any evidence on the candidate was
  CONFLICTING) for a quick review flag.
- **Confirmed:** identifier conflict is a **per-evidence quality** issue. It lowers
  that evidence's contribution only; it never independently forces global
  AMBIGUOUS. Ambiguity is decided solely by competing-callback margins (§4).

---

## Worked examples (expected scores & statuses under this policy)

Using the committed adversarial fixtures. Note: these differ from Phase-1 cascade
numbers because the match-strength multiplier now applies.

### A · `data_transfer_reg_vs_switch` (DataTransfer; no KB symbols/numerics)

| candidate | evidence | basis | group | s_e | confidence |
|---|---|---|---|---|---|
| `bar` | ENUM_CASE, NORMALIZED_NAME | weak | ("token","DataTransfer") | 0.85×0.85 = **0.7225** | 0.7225 |
| `foo` | REGISTRATION_INIT, HEURISTIC (token-only) | weak | ("token","DataTransfer") | 0.80×0.70 = **0.56** | 0.56 |

margin = 0.7225 − 0.56 = **0.1625 ≥ 0.15** → **RESOLVED `bar`**; conflict = [bar 0.7225, foo 0.56].

### B · `scp_dup_registration` (SetChargingProfile; duplicate registrations)

| candidate | evidence | group | s_e | confidence |
|---|---|---|---|---|
| `on_scp` | REG_INIT `{MSG_SET_PROFILE,·}` EXACT | ("site",g_table) | 0.80 | — |
| `on_scp` | REG_INIT `{41,·}` EXACT | ("site",g_table) | 0.80 | — |

one group, max = 0.80 → **RESOLVED `on_scp`, confidence 0.80**, no conflict.
**No inflation** (not `1−0.2² = 0.96`) — the point of same-group max.

### C · `scp_numeric_vs_name` (SetChargingProfile)

| candidate | evidence | basis | group | s_e | confidence |
|---|---|---|---|---|---|
| `store_profile` | REG_INIT numeric 41, EXACT | strong | ("site",g_table) | 0.80×1.0 = **0.80** | 0.80 |
| `handle_set_charging_profile` | NAME_MATCH pattern, NORMALIZED | weak | ("token","SetChargingProfile") | 0.70×0.85 = **0.595** | 0.595 |

margin = 0.205 ≥ 0.15 → **RESOLVED `store_profile`**; conflict = [store_profile 0.80, name 0.595].

### D · synthetic AMBIGUOUS (corroboration + contradiction)

Action X with `ACTION_X`: registration `{ACTION_X, foo}` (EXACT), name `handle_x`→foo
(NORMALIZED), switch `case ACTION_X:`→bar (EXACT).

- `foo`: groups {("site",tableX):0.80, ("token","X"):0.70×0.85=0.595} →
  raw = 1−(1−0.80)(1−0.595) = 1−0.081 = **0.919** (strong group present → cap 0.99).
- `bar`: {("site",switchX):0.85} → **0.85**.

margin = 0.069 < 0.15 → **AMBIGUOUS** (chosen = None); conflict = [foo 0.919, bar 0.85].
Corroboration lifts `foo` above `bar` in raw score, but the margin rule refuses to
pick a winner over a strong independent competitor.

### E · identifier-conflict penalty

Registration `{41, z}` EXACT (0.80) but `action_id` CONFLICTING → capped `M=0.70`
then ×0.5 → **0.28**. Sole candidate `z`: 0.28 < MIN_CONFIDENCE →
**UNRESOLVED (LOW_CONFIDENCE)**. Per-evidence demotion, no forced global ambiguity.

---

## Implementation impact (applied)

`select_corroborate` is now the default policy (commit `4132c1d`). The
multiplier + policy change altered exactly these asserted numbers — correct under
the policy, not regressions:

- `test_handler_resolutions::test_competing_registration_vs_switch…`: margin
  `0.05 → 0.1625`; candidate confidences `0.85/0.80 → 0.7225/0.56`.
- The two `test_resolution` integration asserts (`0.9`, `0.85`) were pinned to
  `selection="cascade"` (they document cascade); a new corroborate integration
  assert covers the default path. Pure `select_cascade`/`consistency` unit tests
  are unaffected.
- New reason `LOW_CONFIDENCE` added to `UnresolvedReason`.

Selection is a policy parameter: `select_cascade` (Phase 1) vs `select_corroborate`
(default). `F2AAnalyzer(selection="cascade")` reverts per-run.

---

## Closed decisions (review sign-off)

All resolved at review; values live in `CalculusConfig`:

1. `WEAK_ONLY_CAP = 0.85` — **approved** (configurable).
2. CONFLICTING penalty `cap 0.70` then `×0.5` — **approved provisionally**;
   pre/post contribution exposed via `score_pre_penalty` / `score` for later
   retuning without manual reconstruction.
3. Optional strong-competitor ambiguity hardening — **not adopted**; kept as a
   disabled hook (`CalculusConfig.strong_competitor_hardening=False`).
4. Below `MIN_CONFIDENCE` → **UNRESOLVED(LOW_CONFIDENCE)** with candidates
   retained (not RESOLVED-flagged-low).
5. Duplicate registrations in one table — **no corroboration**; they share one
   `("site", table)` group and contribute only their max.
6. Weak provenance key — **global `("token", normalized_name)` collapse**
   (conservative); independent weak sites do not corroborate.
7. Dedup survivor — explicit `MATCH_STRENGTH_RANK` table, tested directly.
