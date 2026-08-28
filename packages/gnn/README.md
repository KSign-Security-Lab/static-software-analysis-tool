# gnn — GNN training and evaluation

Trains graph neural networks over the AST and def-use DFG that `ssat` extracts.
It is a *consumer* of the analysis pipeline: `ssat full` writes one JSON per
function, and `gnn.dataset.JsonDataset` reads it.

Until this branch the package was named `agent`, which it never was — there is
no agent here, only a trainer. The LLM agent is a separate package.

## Setup

```bash
uv sync                     # from the repo root
source .venv/bin/activate
```

Needs Python 3.14+, torch 2.9+ and torch-geometric 2.7+. The default wheels are
CPU-only; for GPU, install the CUDA wheels matching your driver.

## Producing training data

```bash
ssat full path/to/sources -o data/train/CWE121_Stack_Based_Buffer_Overflow
```

Each output file carries top-level `ast` and `dfg` keys — the schema
`juliet_json_to_sample` reads. `TrainConfig.data_path` points at these
directories and pairs each with a `LabelKey` (a filename keyword and the label
it implies, e.g. `bad` -> 1).

## Train and evaluate

```bash
gnn train    --save_name results/exp1 --device cuda:0 --epochs 50 --mode ast
gnn evaluate --results_dir results/exp1 --max_samples 200
```

`train` writes weights plus a complete `training_config.json` to
`results/<save_name>/`; `evaluate` reads that file back and reconstructs the
model, so it needs little more than the directory.

`--mode` selects the architecture:

| mode | model | inputs |
| --- | --- | --- |
| `ast` (default) | `ASTOnlyModel` | AST graph only |
| `dfg` | `DFGOnlyModel` | DFG graph only |
| `late_fusion` | `LateFusionModel` | both, fused after encoding |
| `both` | `CreativeGNN` | both, jointly |

## Layout

```
src/gnn/
  config.py            TrainConfig / DataPath / LabelKey (pydantic)
  train.py             training loop, model selection, dataloaders
  evaluate.py          metrics, checkpoint loading
  __init__.py          `gnn train` / `gnn evaluate` entry points
  dataset/
    JsonDataset.py     JSON -> PyG Data; juliet_json_to_sample
    structures.py      dataset-side schemas
  model/               SingleBranch, LateFusion, CreativeGNN
  utils/plotting.py    loss curves
  scripts/
    compare.py         compare runs
    data_analysis.py   parquet-backed graph statistics (polars)
```

## Notes

- Graphs become PyG `Data` with `edge_index` as `2 x num_edges`; batching uses
  a custom collate over `Batch.from_data_list`.
- Labels come from an explicit `label` key when present, otherwise from the
  filename via `LabelKey`. `ssat full` does not emit `label` by default, so the
  filename rule applies — see `training_record()` in `ssat.pipeline`.
- Per-epoch artifacts (`metrics.json`, `roc.png`, `pr.png`, confusion matrices)
  land in `results/<save_name>/epoch_xx/`.
- This package is deliberately outside the `mypy --strict` gate; it is a
  research consumer, not part of the analysis library.
