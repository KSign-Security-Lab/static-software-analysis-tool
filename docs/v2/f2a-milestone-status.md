# F2-A handler resolution — milestone status: COMPLETE

The planned F2-A handler-resolution work is complete. The implementation is frozen
as of commit `c3100e8`; no further F2-A design or implementation iteration is
planned.

| Area | Status |
|---|---|
| Handler-resolution architecture (evidence → candidate → selection) | **COMPLETE** |
| Public output model (`handler_resolutions`; `HandlerMap` back-compat) | **COMPLETE** |
| Evidence calculus (`select_corroborate`: dedup, provenance groups, penalties, noisy-OR, caps, ambiguity/low-confidence) | **COMPLETE** |
| Static evidence producers (string, enum/switch, registration init/indexed, correlated field store, registrar call, name) | **COMPLETE** |
| Evaluation tooling (deterministic harness, locked taxonomy, per-action records) | **COMPLETE** |
| Real-corpus evaluation | **OPTIONAL / SEPARATE WORK ITEM** |
| Deferred stronger analysis backends | **DEMAND-DRIVEN** |

## Original goal — achieved

The registry-dispatched RemoteStart case that motivated this work now resolves
end to end:

```
register_handler(ACTION_REMOTE_START, process_request)
    → REGISTRAR_CALL evidence → process_request candidate
    → corroboration + selection → public HandlerResolution (RESOLVED)
```

The model moved beyond supporting individual syntax patterns to a
producer/evidence/selection architecture.

## Notes carried forward

- **The synthetic harness run is verification only, not an F2-A performance
  result.** Its high `UNKNOWN` count is expected: every fixture is evaluated
  against the full four-action KB, so actions absent from a translation unit
  correctly classify as UNKNOWN (not a deficiency).
- **Real-corpus evaluation is an evaluation activity, not unfinished feature
  work.** When a representative OCPP C/C++ corpus is available, run the harness
  (`python -m ssat.f2a.evaluation --source-dir <repo> --out <dir>`) as a separate
  task. Record unsupported and cross-TU cases exactly as observed; do not optimize
  the harness around the corpus or implement backends during evaluation.
- **Deferred shapes are additive, not missing pieces.** function-pointer /
  aliased registrar targets, aliased args, alias-sensitive variable-index
  correlation, macro-generated registration, and unresolved indirect calls each
  need a stronger backend (indirect-call resolution, points-to/DFG, preprocessing)
  and would enter as new evidence producers or resolvers behind the unchanged
  model. None are assumed in advance; a real-corpus histogram would justify any
  such follow-up project.

## Reference documents

- `f2a-handler-registration-ir.md` — dispatch-shape survey; registration IR.
- `f2a-handler-resolution-model-design.md` — model design + implementation status.
- `f2a-evidence-calculus-spec.md` — the reviewed & implemented calculus.
- `f2a-phase3-evidence-producers-design.md` — correlated field store + registrar call.
- `f2a-evaluation-harness.md` — evaluation tooling reference.
