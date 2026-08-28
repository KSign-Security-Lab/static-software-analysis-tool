import argparse
import json
import os
from typing import List, Optional, Any, Dict
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import (
    ConcatDataset,
    Dataset as TorchDataset,
    Subset,
)

from .dataset.JsonDataset import GenericJsonDataset
from .dataset.JsonDataset import AnyGraphModel, juliet_json_to_sample
from .config import TrainConfig
from gnn.evaluate import evaluate_model, latest_epoch_checkpoint, load_model_robust, infer_mode_from_model
from gnn.utils.plotting import draw_loss_plot
from gnn.train import (
    build_dataloader,
    console,
    Sample,
    infer_dims_from_dataset,
    compute_class_weights,
    select_model,
    collate_multi,
    forward_by_mode,
    train_model_from_dataset,
    save_training_config,
)


def _parse_train_args() -> TrainConfig:
    parser = argparse.ArgumentParser(description="Train GNN model (gnn train)")
    parser.add_argument("--save_name", type=str, default=None, help="Results directory (default uses timestamp)")
    parser.add_argument("--device", type=str, default=None, help="Device like cuda:0 or cpu")
    parser.add_argument("--epochs", type=int, default=None, help="Training epochs")
    parser.add_argument(
        "--mode", type=str, default=None, choices=["both", "late_fusion", "ast", "dfg"], help="Model mode"
    )
    args, _ = parser.parse_known_args()
    cfg = TrainConfig()
    if args.save_name:
        cfg.save_name = args.save_name
    if args.device:
        cfg.device = args.device
    if args.epochs is not None:
        cfg.epochs = int(args.epochs)
    if args.mode:
        cfg.mode = args.mode  # type: ignore[assignment]
    return cfg


def train(cfg: Optional[TrainConfig] = None, *, plot_max_points: Optional[int] = None) -> None:
    if cfg is None:
        # When invoked via console script (gnn train), parse CLI flags
        cfg = _parse_train_args()

    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    device = torch.device(cfg.device)
    console.print(f"Using device: {device}")

    results_dir = cfg.save_name
    os.makedirs(results_dir, exist_ok=True)

    console.print(f"Loading dataset(s) from path(s): {cfg.data_path}")

    train_datasets_list: List[TorchDataset[Sample]] = []
    test_datasets_list: List[TorchDataset[Sample]] = []
    per_dataset_stats: List[dict] = []
    overall_counts: dict[int, int] = {}
    overall_total: int = 0

    for ds_idx, data_entry in enumerate(cfg.data_path):
        # cfg.data_path is a list of DataPath items
        entry_path = data_entry.path
        # Single label key per datapath (required)
        entry_label_key = data_entry.label_key

        # Wrap converter to inject per-entry label_key
        def _conv(m, _lk=entry_label_key):
            return juliet_json_to_sample(m, label_keys=[{"keyword": _lk.keyword, "label": _lk.label}])

        # Inject the filesystem path into JSON before validation, so the converter can use filename
        def _pre_inject_path(raw: dict, fp: str):
            raw["__file_path"] = fp
            return raw

        dataset_part = GenericJsonDataset(
            paths=entry_path,
            model_cls=AnyGraphModel,
            converter=_conv,
            pre=_pre_inject_path,
            strict=False,
            debug=False,
        )
        # Split dataset into train/test using cfg.train_ratio
        n_items = len(dataset_part)
        if n_items > 0:
            gen = torch.Generator()
            gen.manual_seed(int(cfg.seed) + int(ds_idx))
            perm = torch.randperm(n_items, generator=gen).tolist()
        else:
            perm = []
        if n_items <= 1:
            split = n_items  # all to train if <=1
        else:
            split = int(round(n_items * float(cfg.train_ratio)))
            split = max(1, min(n_items - 1, split))
        train_idx = perm[:split]
        test_idx = perm[split:]

        train_datasets_list.append(Subset(dataset_part, train_idx))
        test_datasets_list.append(Subset(dataset_part, test_idx))

        # Compute label statistics for this dataset
        counts: dict[int, int] = {}
        for i in range(len(dataset_part)):
            y = int(dataset_part[i].y.item())
            counts[y] = counts.get(y, 0) + 1
        total_n = len(dataset_part)
        overall_total += total_n
        for k, v in counts.items():
            overall_counts[k] = overall_counts.get(k, 0) + v

        # Build distribution as floats
        dist = {str(k): (v / total_n if total_n > 0 else 0.0) for k, v in counts.items()}
        # Record the label_key used for this dataset for transparency
        used_lk = {"keyword": entry_label_key.keyword, "label": int(entry_label_key.label)}

        per_dataset_stats.append(
            {
                "path": entry_path,
                "num_samples": total_n,
                "label_counts": {str(k): int(v) for k, v in counts.items()},
                "label_distribution": dist,
                "label_key": used_lk,
            }
        )

    # Save statistics JSON (per dataset and overall)
    overall_dist = {str(k): (v / overall_total if overall_total > 0 else 0.0) for k, v in overall_counts.items()}
    stats_out = {
        "datasets": per_dataset_stats,
        "overall": {
            "num_samples": int(overall_total),
            "label_counts": {str(k): int(v) for k, v in overall_counts.items()},
            "label_distribution": overall_dist,
        },
    }
    with open(os.path.join(results_dir, "dataset_statistics.json"), "w") as f:
        json.dump(stats_out, f, indent=2)
    console.print(
        f"Saved dataset statistics → {os.path.join(results_dir, 'dataset_statistics.json')}",
        style="green",
    )

    # Declare item type for sources, then build a typed ConcatDataset[Sample]
    train_dataset: ConcatDataset[Sample] = ConcatDataset(train_datasets_list)  # type: ignore[arg-type]
    test_dataset: ConcatDataset[Sample] = ConcatDataset(test_datasets_list)  # type: ignore[arg-type]

    # Decide which graph kinds to probe based on mode
    kinds = ["ast"] if cfg.mode == "ast" else ["dfg"] if cfg.mode == "dfg" else ["ast", "dfg"]

    ast_in = ast_edge_dim = dfg_in = dfg_edge_dim = 0

    # ConcatDataset[Sample] structurally satisfies SupportsIndex[Sample]
    inferred = infer_dims_from_dataset(train_dataset, kinds)
    ast_in = inferred.get("ast", (0, 0))[0]
    ast_edge_dim = inferred.get("ast", (0, 0))[1]
    dfg_in = inferred.get("dfg", (0, 0))[0]
    dfg_edge_dim = inferred.get("dfg", (0, 0))[1]
    console.print(
        f"Inferred dims → ast: x={ast_in}, edge_attr={ast_edge_dim}; dfg: x={dfg_in}, edge_attr={dfg_edge_dim}"
    )

    class_weights = compute_class_weights(list(range(len(train_dataset))), train_dataset, num_classes=2).to(device)

    console.print(f"Class weights: {class_weights}")

    train_dataloader = build_dataloader(train_dataset, cfg, collate_fn=collate_multi)
    test_dataloader = build_dataloader(test_dataset, cfg, collate_fn=collate_multi)

    model = select_model(
        cfg=cfg,
        ast_in=ast_in,
        dfg_in=dfg_in,
        edge_dim_ast=ast_edge_dim,
        edge_dim_dfg=dfg_edge_dim,
    )
    console.print(f"Model created: {cfg.mode} mode")
    model.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    def local_forward(m, b, d, mode=cfg.mode):
        return forward_by_mode(m, b, d, mode)

    iter_losses: List[float] = []
    epoch_avg_losses: List[float] = []

    train_model_from_dataset(
        cfg=cfg,
        dataloader=train_dataloader,
        model=model,
        optimizer=optimizer,
        criterion=criterion,
        device=device,
        local_forward=local_forward,
        iter_losses=iter_losses,
        epoch_avg_losses=epoch_avg_losses,
        results_dir=results_dir,
    )

    # Save final weights (state_dict)
    weights_path = os.path.join(results_dir, "model.pt")
    torch.save(model.state_dict(), weights_path)

    # Persist per-iteration losses as JSON/CSV for analysis
    with open(os.path.join(results_dir, "loss.json"), "w") as f:
        json.dump(
            {"iteration_losses": iter_losses, "epoch_avg_losses": epoch_avg_losses},
            f,
            indent=2,
        )
    with open(os.path.join(results_dir, "loss.csv"), "w") as f:
        f.write("iteration,loss\n")
        for i, loss in enumerate(iter_losses, start=1):
            f.write(f"{i},{loss}\n")
    console.print(f"Saved loss history → {os.path.join(results_dir, 'loss.json')} and loss.png")

    # Plot with downsampling
    draw_loss_plot(results_dir, iter_losses, epoch_avg_losses, max_points=plot_max_points)

    # Save training configuration for evaluation
    model_info = {
        "model_type": cfg.mode,
        "model_class": model.__class__.__name__,
        "ast_in": int(ast_in),
        "ast_edge_dim": int(ast_edge_dim),
        "dfg_in": int(dfg_in),
        "dfg_edge_dim": int(dfg_edge_dim),
    }
    save_training_config(cfg, results_dir, model_info)

    summary = evaluate_model(
        model=model,
        dataloader=test_dataloader,
        device=device,
        mode=cfg.mode,
        max_samples=len(test_dataset),
    )

    with open(os.path.join(results_dir, "evaluation.json"), "w") as f:
        json.dump(summary, f, indent=2)


def evaluate() -> None:
    """Console entrypoint: gnn evaluate --results_dir <dir> [--device cuda:0] [--max_samples N]

    Reconstructs the dataset and model from training_config.json in results_dir
    and writes evaluation.json alongside.
    """
    parser = argparse.ArgumentParser(description="Evaluate trained model (gnn evaluate)")
    parser.add_argument(
        "--results_dir", type=str, required=True, help="Directory containing training_config.json and checkpoints"
    )
    parser.add_argument("--device", type=str, default=None, help="Device like cuda:0 or cpu")
    parser.add_argument("--max_samples", type=int, default=100, help="Max samples to evaluate (default: 100)")
    args, _ = parser.parse_known_args()

    results_dir = args.results_dir
    cfg_path = os.path.join(results_dir, "training_config.json")
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"training_config.json not found at: {cfg_path}")

    with open(cfg_path, "r") as f:
        saved: Dict[str, Any] = json.load(f)
    saved_cfg = saved.get("training_config", {})
    cfg = TrainConfig(**saved_cfg)
    if args.device:
        cfg.device = args.device

    device = torch.device(cfg.device)

    # Rebuild datasets consistent with training config
    train_datasets_list: List[TorchDataset[Sample]] = []
    test_datasets_list: List[TorchDataset[Sample]] = []
    for ds_idx, data_entry in enumerate(cfg.data_path):
        entry_path = data_entry.path
        entry_label_key = data_entry.label_key

        def _conv(m, _lk=entry_label_key):
            return juliet_json_to_sample(m, label_keys=[{"keyword": _lk.keyword, "label": _lk.label}])

        def _pre_inject_path(raw: dict, fp: str):
            raw["__file_path"] = fp
            return raw

        dataset_part = GenericJsonDataset(
            paths=entry_path,
            model_cls=AnyGraphModel,
            converter=_conv,
            pre=_pre_inject_path,
            strict=False,
            debug=False,
        )
        n_items = len(dataset_part)
        if n_items > 0:
            gen = torch.Generator()
            gen.manual_seed(int(cfg.seed) + int(ds_idx))
            perm = torch.randperm(n_items, generator=gen).tolist()
        else:
            perm = []
        if n_items <= 1:
            split = n_items
        else:
            split = int(round(n_items * float(cfg.train_ratio)))
            split = max(1, min(n_items - 1, split))
        train_idx = perm[:split]
        test_idx = perm[split:]
        train_datasets_list.append(Subset(dataset_part, train_idx))
        test_datasets_list.append(Subset(dataset_part, test_idx))

    test_dataset: ConcatDataset[Sample] = ConcatDataset(test_datasets_list)  # type: ignore[arg-type]

    # Determine dims and model
    kinds = ["ast"] if cfg.mode == "ast" else ["dfg"] if cfg.mode == "dfg" else ["ast", "dfg"]
    inferred = infer_dims_from_dataset(test_dataset, kinds)
    ast_in = inferred.get("ast", (0, 0))[0]
    ast_edge_dim = inferred.get("ast", (0, 0))[1]
    dfg_in = inferred.get("dfg", (0, 0))[0]
    dfg_edge_dim = inferred.get("dfg", (0, 0))[1]

    model = select_model(
        cfg=cfg,
        ast_in=ast_in,
        dfg_in=dfg_in,
        edge_dim_ast=ast_edge_dim,
        edge_dim_dfg=dfg_edge_dim,
    )
    model_path = latest_epoch_checkpoint(results_dir) or os.path.join(results_dir, "model.pt")
    model = load_model_robust(model_path, device)
    mode = infer_mode_from_model(model)

    dataloader = build_dataloader(test_dataset, cfg, collate_fn=collate_multi)
    per_sample_out = os.path.join(results_dir, "evaluation")
    os.makedirs(per_sample_out, exist_ok=True)
    summary = evaluate_model(
        model=model,
        dataloader=dataloader,
        device=device,
        mode=mode,
        max_samples=int(args.max_samples),
        output_dir=per_sample_out,
        forward_fn=None,
    )

    summary_file = os.path.join(results_dir, "evaluation.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    console.print(f"Saved evaluation summary → {summary_file}", style="green")


def main() -> None:
    """Top-level entry point.

    Example:
      gnn train --save_name results/exp1
      gnn evaluate --results_dir results/exp1
    """
    parser = argparse.ArgumentParser(prog="gnn", description="SSAT GNN training and evaluation")
    parser.add_argument("command", nargs="?", choices=["train", "evaluate"], help="Subcommand to run")
    args, _passthrough = parser.parse_known_args()
    if args.command == "train":
        train()
    elif args.command == "evaluate":
        evaluate()
    else:
        parser.print_help()
