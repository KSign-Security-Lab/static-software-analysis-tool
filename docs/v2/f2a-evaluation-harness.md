# F2-A evaluation harness

**Status: IMPLEMENTED (first increment — corpus-agnostic, no backend added).**
`ssat/f2a/evaluation.py`.

Runs the handler resolver over a corpus and produces a deterministic JSON report
plus a Markdown summary. It is evaluation tooling only: it never resolves handlers
itself, adds no dispatch backend, and does not change the calculus.

## Inputs

- **CPG mode:** a directory of pre-generated CPG GraphSON `.json` files
  (`evaluate_cpg_dir` / `--cpg-dir`).
- **Source mode:** a directory of C/C++ sources, one CPG per file via embedded
  Joern (`evaluate_source_dir` / `--source-dir`; imported lazily so CPG mode
  needs no JVM).

```
python -m ssat.f2a.evaluation --cpg-dir <dir> --corpus-id <id> --out <out_dir>
python -m ssat.f2a.evaluation --source-dir <dir> --corpus-id <id> --out <out_dir>
```

## Report structure

- `run` — identity, so runs with different thresholds/graph settings never look
  equivalent: `tool_commit`, `calculus_config`, `corpus_id`,
  `cpg_generation_config`, `timestamp`. (Metadata; excluded from determinism.)
- `metrics` — the five approved areas (deterministic):
  1. `outcome_counts` — RESOLVED / AMBIGUOUS / UNRESOLVED;
  2. `unresolved_reason_histogram` + `tier_histogram` (analysis-scope separation);
  3. `backend_histogram` — likely backend required, split by classification
     confidence;
  4. `resolved_confidence`, `corroboration_lift`, `margin`,
     `within_ambiguity_margin` distributions;
  5. `evidence_volume`, `candidate_volume`.
- `actions` — **per-action records** (deterministic), retained so misclassifications
  and surprising scores are inspectable/reproducible: corpus file, action, status,
  chosen function, unresolved reason, candidate/evidence counts, evidence kinds,
  top/runner-up confidence, margin, corroboration lift, and the classification.
- `performance` — wall-clock runtime (non-deterministic; excluded from equality).

`deterministic_view(report)` returns `{metrics, actions}` for run-to-run
comparison.

## Classification taxonomy (locked)

```
UNRESOLVED
├── ANALYSIS_SCOPE
│   ├── EXTERNAL_DEFINITION
│   ├── CROSS_TU_REGISTRATION
│   └── MISSING_CPG_RELATION
├── POTENTIALLY_SUPPORTABLE
│   ├── INDIRECT_CALL
│   ├── ALIAS_OR_POINTS_TO
│   ├── VARIABLE_INDEX_CORRELATION
│   └── PREPROCESSOR_OR_MACRO
├── POLICY
│   ├── LOW_CONFIDENCE
│   └── COMPETING_CANDIDATES
└── UNKNOWN
```

Every classification carries `backend_category`, `classification_confidence`
(HIGH / MEDIUM / LOW), and `supporting_observations`. **The classifier never
claims certainty when the information is absent** — e.g. an unresolved indirect
call is `INDIRECT_CALL` at MEDIUM with "alternative: cross-TU external
definition" recorded, and a `NO_EVIDENCE` action that is *not referenced* in the
TU is `UNKNOWN` (LOW), not a false `CROSS_TU_REGISTRATION`. Cross-TU is only
asserted (MEDIUM) when the action id is observably referenced but unregistered —
keeping the cross-TU dimension first-class and separate from supportable-shape
gaps.

## Synthetic smoke run (committed fixtures, 15 CPGs × 4 KB actions = 60 slots)

Deterministic; used only to verify output stability and metric correctness (not a
representative measurement):

- outcomes: 13 RESOLVED, 1 AMBIGUOUS, 46 UNRESOLVED;
- tiers: POLICY 1, POTENTIALLY_SUPPORTABLE 4, UNKNOWN 42 (actions absent from a TU);
- reasons: NO_EVIDENCE 42, UNRESOLVED_INDIRECT_CALL 3, REGISTRAR_STORE_NOT_REACHED 1;
- resolved confidence: min 0.595 / median 0.8 / max 0.9595.

Pinned by `tests/test_evaluation.py` (determinism, taxonomy, per-action
traceability, scope/supportable separation).

## Next step (not done here)

Run against one real open-source OCPP C/C++ implementation as the first external
corpus. Do **not** optimize the harness around it or implement missing backends
during evaluation; record unsupported and cross-TU cases exactly as observed. The
resulting histograms decide whether the next investment is indirect-call
resolution, alias-aware slot correlation, macro/preprocessor support, or no
further F2-A work.
