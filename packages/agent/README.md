# GNN Model Training and Evaluation

This package provides a modular GNN training/evaluation pipeline with PyTorch Geometric batching, automatic training-config saving, and a streamlined evaluation entrypoint.

## Structure

```bash
packages/agent/
├── train.py                    # Training entrypoint (saves training_config.json)
├── evaluate.py                 # Evaluation entrypoint (loads training_config.json)
├── oneclick.py                 # Run one or more experiments sequentially/parallel
├── modules/
│   ├── dataset.py              # HF streaming, PyG graph building, collate fn
│   ├── evaluation.py           # analyze_sample_with_model, evaluate_model
│   └── dataset_split.py        # load_training_config, create_model_from_config
├── model/                      # Model definitions
├── utils/explain.py            # GNN explanation utilities
└── README.md                   # This file
```

## Quick Start

### Train

```bash
cd packages/agent
python train.py --save_name default --device cuda:0
```

- Uses the default HF dataset `keonoh00/static-software-analysis-dataset` unless overridden in `TrainConfig`.
- Saves weights and full config to `results/<save_name>/training_config.json`.

### Evaluate (auto-config)

```bash
cd packages/agent
python evaluate.py --results_dir results/default
```

- Loads `results/<save_name>/training_config.json` and reconstructs the model and defaults.
- Optional overrides: `--split`, `--max_samples`, `--device`, `--output_file`.

## Programmatic Usage

### Training

```python
from train import TrainConfig, train

cfg = TrainConfig(
    save_name="exp1",
    device="cuda:0",
    epochs=50,
    # repo_id has a default; override if needed
)
train(cfg)
```

### Evaluation

```python
from modules.dataset_split import load_training_config, create_model_from_config
from modules.evaluation import evaluate_model
import torch

config = load_training_config("results/exp1")
device = torch.device("cuda:0")
model = create_model_from_config(config, device)

# See evaluate.py for the full loop; below is a minimal sketch
summary = evaluate_model(model=model, repo_id=config["training_config"]["repo_id"], split="test", device=device)
print(summary)
```

## Data Loading Notes

- Graphs are converted into PyG `Data` using `_build_pyg_from_ast_item`/`_build_pyg_from_dfg_item`.
- Batching uses a `custom_collate_fn` with `torch_geometric.data.Batch.from_data_list`.
- `edge_index` is built from the first two columns of edges (src, dst).

## Saved Configuration

Training writes a complete configuration file for reproducibility:

```bash
results/<save_name>/training_config.json
```

Contents include:

- `training_config` (serialized `TrainConfig`)
- `model_info` and `training_metadata`

Evaluation consumes this file to minimize CLI arguments.

## Running Multiple Experiments

- `oneclick.py` contains a list of `TrainConfig` objects and runs them sequentially by default.
- For parallel runs, enable a multiprocessing block (ensure CUDA safety on your system). If you encounter CUDA initialization errors, prefer sequential execution.

## CUDA/Multi-processing Tips

- Recommended: run one experiment per GPU (e.g., `device="cuda:0"`).
- If using multiprocessing, methods like `forkserver` or `spawn` may be more reliable than `fork` with CUDA.
- Always prefer graceful termination; ensure child processes are cleaned up if you customize parallel execution.

## Known Fixes Incorporated

- Iterable dataset length handling and safe metrics (probabilities vs predictions).
- PyG batching via custom collate function.
- Correct `edge_index` shape (2 x num_edges).
- Unified training/evaluation data loading.
- `create_model_from_config` aligns with saved model hyperparameters.

## Results

Artifacts (per-epoch) are saved under `results/<save_name>/epoch_xx/`, including `metrics.json`, `roc.png`, `pr.png`, and confusion matrices.
