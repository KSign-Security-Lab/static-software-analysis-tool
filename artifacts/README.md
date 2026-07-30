# artifacts/

Scratch, generated output and evaluation corpora. **Nothing here is source.**
The whole directory is gitignored; delete any of it and the repo still builds.

| path | what it is |
| --- | --- |
| `result/`, `results/` | generated CPG / template / AST / DFG output from past runs |
| `open-ocpp/` | OCPP evaluation corpus, checked out locally (not vendored) |
| `ksigncase64/` | sample corpus |
| `workspace/` | Joern container scratch (`docker-compose.yml` bind-mounts this) |
| `workspace-devel02/` | another user's leftover scratch |
| `node_modules/` | orphaned deps from the pre-migration yarn workspace |
| `docs-latex/` | orphaned LaTeX build output; the `.tex` source no longer exists |

Regenerate analysis output with `ssat <mode> -d <input> -o <dir>`.
