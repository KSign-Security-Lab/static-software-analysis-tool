# Is the Python Template converter the same as the TypeScript it replaced?

**No — but close.** The port kept every dispatch table, every handler and the whole
orchestration intact. It diverges at the value-coercion boundaries, in eight measurable
classes, and it introduced one bug that makes the stage's own output non-reproducible.

| | |
|---|---|
| TypeScript read at | `23c411b^` = `75252f1`, `packages/core/template/` |
| Python read at | `feat/agentic-approach`, `packages/ssat/src/ssat/template/` |
| Inputs | 19 C fixture CPGs + `fixtures/java/Sample.json` (5.9 MB) |
| Method | pairwise reading + differential execution |
| Result | 8 divergence classes · 20 inputs compared · 0 crashes either side · 0 node-census differences |

Both implementations produce the same node types, in the same quantities, in the same tree
shape, on all 20 inputs. What differs is the content of four fields and the order of the
root array. Nothing in the analysis output changes as a result — but nothing in the
analysis output was checking, either.

> Scope note: only the **Template** stage is a genuine TypeScript → Python port. The AST
> extractor was already Python before the migration (`endpoint/index.ts` shelled out to
> `ASTExtractor.py` through `python-shell`), so there is no TypeScript AST logic to compare.
> `DFGBuilder.ts` (670 lines, features derived by regex over `CODE`) was abandoned rather
> than ported; today's `dfg/extractor.py` descends from the Python extractor that ran beside
> it. CFG was never converted in either language: the TypeScript's `CPGFilter.filterDFG()`
> filtered `CFG`/`CDG` edges despite its name and had no callers, and the only CFG that
> exists now is `cfgView()` in `web/lib/views.ts`, a projection of the raw CPG by edge label.

---

## What matched exactly

Worth stating first, because it is most of the surface area and it means the divergences
below are local rather than systemic.

- **All three operator tables**, byte-for-byte after syntax normalisation:
  `BinaryExpressionOperatorMap` (25), `BinaryExpressionBooleanMap` (8),
  `UnaryExpressionOperatorMap` (13), `PredefinedIdentifierTypes` (7),
  `IdentifierToLiteralMap`.
- **The label dispatch**: the same 11 skipped labels, the same 17 handler mappings, the same
  default → raise.
- **The operator dispatch and its order**: binary map → unary map → `addressOf` →
  `assignment` → `cast` → `fieldAccess`/`indirectFieldAccess` → `indirectIndexAccess` →
  `sizeOf` → passthrough.
- **The control-structure dispatch**, all seven kinds, including the `IF` child re-ordering
  and `SWITCH` going through `reshapeLabelChildren`.
- **The orchestrator**: same four stages in the same order, the same 19-entry
  `PlanationTool` blacklist in the same order, the same
  `TreeToText(["properties","line_no","code"])`, the same duplicate-id assertion. Both skip
  `mergeArraySizeAllocation` and `isolateTranslationUnit`.
- **Node census and tree shape** on every input: 20/20 identical, and the root *multiset* is
  identical on 20/20.

---

## Divergences

Ordered by consequence. **loss** = information the TypeScript produced and the Python does
not. **drift** = both produce a value and the values differ. **cosmetic** = same
information, different wire shape. Counts are node occurrences across the 19 C fixtures.

### 1. Root order is not merely different — it is non-deterministic

`loss` · **8 / 19 fixtures differ from TS**

The TypeScript builds its root set from a JS `Set`, which preserves insertion order, so roots
come out in CPG vertex order. The Python iterates a Python `set`, whose order is
hash-derived — and `str` hashing is randomised per process.

```ts
// TypeScript — TemplateExtractor.ts:86
const allIds = new Set<string>(Object.keys(nodeInfoMap));   // insertion-ordered
const childIds = new Set<string>();
```

```python
# Python — extractor.py:72,77
all_ids = set(node_info_map.keys())
...
root_ids = [rid for rid in all_ids if rid not in child_ids]
```

Demonstrated on `update_firmware.c`: across three fresh processes, `TranslationUnit` came
back at root index **0**, then **20**, then **20**. Under fixed seeds, `PYTHONHASHSEED=0,1`
put it last and `2,12345` put it first.

**Reaches:** the array order of every `*_template.json` artifact and of `POST /template`.
Function order is *currently* safe by luck — all 19 fixtures have exactly one
function-bearing root, so the shuffle only moves orphan roots around it. A CPG with two
file-level roots would make function order flake too, and the golden snapshots would not
catch it: they record `template_root_count`, a count, not an order.

### 2. `storage` is dropped on every declaration whose type name is not literally in its code

`loss` · **145 nodes** (91 `VariableDeclaration`, 28 `ArrayDeclaration`, 26 `PointerDeclaration`)

When the type name does not occur in the declaration's source text, JS `split` returns a
one-element array and the TypeScript takes the whole code string. The Python added a
`len(parts) > 1` guard and returns `None` there instead.

```ts
// TypeScript — TemplateConverter.ts (handleLocal)
const storage =
  node.code.includes(typeFullName) && node.code.trim().startsWith(typeFullName)
    ? undefined
    : node.code.split(typeFullName)[0].trim();
```

```python
# Python — converter.py (_handle_local)
elif type_full_name_str:
    parts = code.split(type_full_name_str)
    storage = parts[0].strip() if len(parts) > 1 else None
```

The TypeScript values were largely nonsense for a field named "storage" — `"char sql[512]"`,
`"*data"`, `"ACTION_BOOT_NOTIFICATION = 1"` — so the Python is arguably more honest. It is
still a silent behaviour change.

**Reaches:** one consumer, `ast/extractor.py:830`, which puts it in `debug_extra` for
`PointerDeclaration` only. No feature, no edge, no verdict depends on it — so this degrades
debug output rather than analysis. Visible in
`artifacts/sample/loop_induction_unresolved_guard_template.json`: every `storage` is `null`.

### 3. The `<not-array>` marker is lost inside `PointerDereference`

`loss` · **88 nodes**

Both handlers compute `size` the same way and both attach it to a bare `Identifier` only
when it is an array. But in the pointer-dereference branch the TypeScript passes the
computed `size` through unconditionally, so a non-array identifier carries the sentinel
`"<not-array>"`. The Python re-tests `is_array` and writes `None`.

```ts
// TypeScript — handleIdentifier, pointer branch
children: [{
  nodeType: TemplateNodeTypes.Identifier,
  name: node.name,
  type: predefinedType ?? type,
  size,                          // ← unconditional
  ...
```

```python
# Python — _handle_identifier, pointer branch
{
  "nodeType": TemplateNodeTypes.Identifier,
  "name": node_name,
  "type": predefined_type or type_val,
  "size": size if is_array else None,     # ← re-tested
  ...
```

**Reaches:** nothing. No reader of `Identifier.size` exists in `ast/`, `dfg/` or `nodes/` —
the only `size` lookups there are call-argument slots, an unrelated table. The field is dead
data on both sides, which is why the loss went unnoticed.

### 4. The `<dynamic>` fallback for an unsized array was not ported

`drift` · **12 nodes**

For `char[]` — brackets present, nothing between them — the TypeScript's `||` substitutes
the sentinel. The Python has no fallback and yields the empty string.

```ts
// TypeScript — handleIdentifier
const size = isArray
  ? typeFullName.split("[")[1].split("]")[0] || "<dynamic>"
  : "<not-array>";
```

```python
# Python — _handle_identifier
size = type_full_name_str.split("[")[1].split("]")[0] if is_array else "<not-array>"
#      ^ no fallback → ""
```

**Reaches:** nothing today, for the same reason as above. But `""` is falsy where
`"<dynamic>"` is truthy, so any future reader that tests the field will read "unsized array"
as "no information".

### 5. Pointer types lose every `*`, not just the first

`drift` · **1 observed, latent beyond**

JS `String.replace` with a string pattern replaces the *first* match only; Python's
`str.replace` replaces all of them. So a double pointer keeps one star in the TypeScript and
loses both in the Python.

```ts
// TypeScript — handleLocal / handleIdentifier
const pointsTo = typeFullName.replace("*", "");
// "char**"        → "char*"
// "void()(void*)" → "void()(void)"   ← observed
```

```python
# Python — converter.py:15, 508, 646
points_to = type_full_name_str.replace("*", "")
# "char**"        → "char"
# "void()(void*)" → "void()(void)"
```

Caught by the differential run on `designated_init_negatives.c`, as
`PointerDeclaration.pointingType`. Only one occurrence in the fixture set because double
pointers are rare in it — `level` is computed separately and correctly on both sides, so the
star count itself is not lost.

**Reaches:** `ast/extractor.py:828`, again as `debug_extra` for `PointerDeclaration`.
Cosmetic today; wrong if anything ever matches on the pointee type.

### 6. Optional fields are `null` in Python where they are absent in TypeScript

`cosmetic` · **483 nodes**

`JSON.stringify` drops keys whose value is `undefined`; Python emits `null`. Same
information, different wire shape — but `"size" in node` answers differently, and so does any
schema that distinguishes absent from null.

| Field | Count | TypeScript | Python |
|---|---:|---|---|
| `ParameterDeclaration.size` | 289 | key absent | `null` |
| `ParameterList.code` | 100 | key absent | `null` |
| `Identifier.code` | 88 | key absent | `null` |
| `VariableDeclaration.storage` | 6 | key absent | `null` |

**Reaches:** anything comparing a pre-migration artifact to a post-migration one, which is
exactly what a "did the port change anything" check would do. Nothing in the pipeline itself
distinguishes the two.

### 7. Two numeric coercions disagree, on inputs Joern does not currently produce

`drift` · `latent`

Found by reading, not by the differential run — the fixtures never hit them, which is
precisely why both methods were needed.

| Site | TypeScript | Python | Disagrees when |
|---|---|---|---|
| `id`, every handler | `Number(node.id) \|\| -999` | `int(...) if str(...).isdigit() else -999` | id is `0` (TS → `-999`, PY → `0`) or negative (TS keeps it, PY → `-999`) |
| `length`, array decl + alloc | `Number(raw) \|\| raw` | `int(raw) if raw.isdigit() else raw` | `char[0]` — TS yields the string `"0"`, PY the int `0` |

**Reaches:** the `length` one passes through `ast/extractor.py:1483`, which branches on
`isinstance(length, str)` — so TS took the direct path and Python falls through to a regex
over `code`, arriving at the same value by coincidence rather than by design.

---

## Three things that turned out not to be true

Each was a reasonable expectation going in. The differential run contradicted all three.

**The `<operator>.alloc` crash was *not* inherited from the TypeScript.** Nothing threw on
either side. The TypeScript read the property with `.join("/")` and handled it fine. The
crash the tests describe — "returned the property list where callers expected the scalar",
4/19 fixtures and ~37% of the corpus (`legacy_chain.py:37-42`,
`test_characterization.py:42-52`) — was **introduced by the port** and later fixed by
`_unwrap_graphson_scalar`. The Python is now *better* than the TypeScript here, not restored
to it.

**`PostProcessor.updateMemberAccessTypeLength` is not a lost feature.** It is dead in the
TypeScript too: no caller, and it `throw`s on success. It accounts for the entire 282 → 177
line gap between the two `PostProcessor`s. Not a regression.

**`Sample.json` does not cover the Java front end.** Both implementations extract **zero
functions** from it — 104 roots, no `FunctionDefinition`. `handleMethod`'s gate requires
`FILENAME + ":<global>" == AST_PARENT_FULL_NAME`, which Java's class-parented methods never
satisfy. Identical in both, so not a migration issue — but the test asserting it "converts"
only asserts the template is non-empty.

---

## How this was checked

Two independent methods, because neither alone is sufficient: reading finds the latent
coercions the fixtures never reach, and execution finds what 800 lines of reading misses.

The TypeScript was exported read-only with `git archive` — never checked out — transpiled
with the `tsc` already in `web/node_modules`, and driven through the same four stages in the
same order as the Python. It needed no dependency install: the template modules import only
local types, config and `randomIntWithLength`. Both sides' synthetic-id RNG was stubbed to a
function of its own argument, so a mismatch in the argument would still surface as a diff.
Nothing was written into the repo; the working tree was untouched and
`pytest packages/ssat` was green at 190 passed.

```bash
git archive 23c411b^ packages/core | tar -x -C $S/src
web/node_modules/.bin/tsc --module commonjs --moduleResolution node \
  --target es2022 --skipLibCheck --outDir $S/js --rootDir packages/core \
  packages/core/template/*.ts packages/core/utils/treeToText.ts

node $S/js/driver.js <cpg.json>              # getTemplateTree → convertTree
uv run python $S/py_driver.py <cpg.json>     # → removeInvalidNodes → addCodeProperties
python3 $S/aggregate.py $S/out               # census, root order, per-field diff classes
```

An HTML rendering of this report sits beside it at `template-port-audit.html`.
