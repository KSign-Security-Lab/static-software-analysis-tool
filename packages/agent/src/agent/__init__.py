import argparse
import json
import os
from typing import (
    List,
    cast,
)
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import (
    ConcatDataset,
    Dataset as TorchDataset,
)

from .dataset.JsonDataset import GenericJsonDataset
from .dataset.JsonDataset import AnyGraphModel, juliet_json_to_sample
from .config import TrainConfig
from agent.evaluate import (
    evaluate_model,
    infer_mode_from_model,
    latest_epoch_checkpoint,
)
from agent.config import TrainConfig
from agent.train import (
    build_dataloader,
    console,
    Sample,
    infer_dims_from_dataset,
    compute_class_weights,
    select_model,
    collate_multi,
    forward_by_mode,
    ForwardFn,
    train_model_from_dataset,
    save_training_config,
)


def train() -> None:
    cfg = TrainConfig()

    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    device = torch.device(cfg.device)
    console.print(f"Using device: {device}")

    results_dir = cfg.save_name
    os.makedirs(results_dir, exist_ok=True)

    console.print(f"Loading dataset(s) from path(s): {cfg.data_path}")

    train_datasets_list: List[GenericJsonDataset] = []
    test_datasets_list: List[GenericJsonDataset] = []

    # Collect per-dataset statistics prior to concatenation
    per_dataset_stats: List[dict] = []
    overall_counts: dict[int, int] = {}
    overall_total: int = 0

    def _safe_label(val: object) -> int:
        try:
            if isinstance(val, torch.Tensor):
                return int(val.item())
            return int(val)  # type: ignore[arg-type]
        except Exception:
            return 0

    for data_entry in cfg.data_path:
        # cfg.data_path is a list of DataPath items
        entry_path = data_entry.path
        # Single label key per datapath (required)
        entry_label_key = data_entry.label_key

        # Wrap converter to inject per-entry label_key
        def _conv(m, _lk=entry_label_key):
            lks = None
            if _lk:
                try:
                    # juliet_json_to_sample expects a list of mappings; wrap single key
                    if hasattr(_lk, "keyword"):
                        lks = [{"keyword": _lk.keyword, "label": _lk.label}]
                    elif isinstance(_lk, dict) and "keyword" in _lk:
                        lks = [{"keyword": str(_lk["keyword"]), "label": int(_lk.get("label", 0))}]
                except Exception:
                    lks = None
            return juliet_json_to_sample(m, label_keys=lks)

        # Inject the filesystem path into JSON before validation, so the converter can use filename
        def _pre_inject_path(raw: dict, fp: str):
            try:
                raw["__file_path"] = fp
            except Exception:
                pass
            return raw

        dataset_part = GenericJsonDataset(
            paths=entry_path,
            model_cls=AnyGraphModel,
            converter=_conv,
            pre=_pre_inject_path,
            strict=False,
            debug=False,
        )
        train_datasets_list.append(dataset_part)
        test_datasets_list.append(dataset_part)

        # Compute label statistics for this dataset
        counts: dict[int, int] = {}
        for i in range(len(dataset_part)):
            try:
                y_val = getattr(dataset_part[i], "y", 0)
            except Exception:
                y_val = 0
            y = _safe_label(y_val)
            counts[y] = counts.get(y, 0) + 1
        total_n = len(dataset_part)
        overall_total += total_n
        for k, v in counts.items():
            overall_counts[k] = overall_counts.get(k, 0) + v

        # Build distribution as floats
        dist = {str(k): (v / total_n if total_n > 0 else 0.0) for k, v in counts.items()}
        # Record the label_key used for this dataset for transparency
        used_lk = None
        if entry_label_key is not None:
            if hasattr(entry_label_key, "keyword"):
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
    try:
        overall_dist = {
            str(k): (v / overall_total if overall_total > 0 else 0.0) for k, v in overall_counts.items()
        }
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
    except Exception as e:
        console.print(f"[yellow]Failed to save dataset statistics: {e}")

    # Declare item type for sources, then build a typed ConcatDataset[Sample]
    train_sources: List[TorchDataset[Sample]] = [
        cast(TorchDataset[Sample], d) for d in train_datasets_list
    ]
    test_sources: List[TorchDataset[Sample]] = [
        cast(TorchDataset[Sample], d) for d in test_datasets_list
    ]

    train_dataset: ConcatDataset[Sample] = ConcatDataset(train_sources)
    test_dataset: ConcatDataset[Sample] = ConcatDataset(test_sources)

    # Decide which graph kinds to probe based on mode
    if cfg.mode == "ast":
        kinds = ["ast"]
    elif cfg.mode == "dfg":
        kinds = ["dfg"]
    else:
        kinds = ["ast", "dfg"]

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

    class_weights = compute_class_weights(
        list(range(len(train_dataset))), train_dataset, num_classes=2
    ).to(device)

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

    optimizer = torch.optim.Adam(
        model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
    )
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    local_forward: ForwardFn = lambda m, b, d, mode=cfg.mode: forward_by_mode(
        m, b, d, mode
    )

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

    # Save final weights: prefer state_dict for PyTorch >= 2.6
    weights_path = os.path.join(results_dir, "model.pt")
    try:
        torch.save(model.state_dict(), weights_path)
    except Exception:
        # Fallback to saving the full model object
        torch.save(model, weights_path)

    # Persist per-iteration losses as JSON/CSV for analysis
    try:
        with open(os.path.join(results_dir, "loss.json"), "w") as f:
            json.dump(
                {"iteration_losses": iter_losses, "epoch_avg_losses": epoch_avg_losses},
                f,
                indent=2,
            )
        with open(os.path.join(results_dir, "loss.csv"), "w") as f:
            f.write("iteration,loss\n")
            for i, l in enumerate(iter_losses, start=1):
                f.write(f"{i},{l}\n")
        console.print(
            f"Saved loss history → {os.path.join(results_dir, 'loss.json')} and loss.png"
        )
    except Exception as e:
        console.print(f"[yellow]Failed to save loss history files: {e}")

    # Plot all loss series into a single figure at the end
    try:
        plt.figure(figsize=(7, 4.5))
        # Per-iteration curve
        if iter_losses:
            plt.plot(
                range(1, len(iter_losses) + 1),
                iter_losses,
                label="train (iter)",
                linewidth=1.2,
            )
        # Epoch averages overlay at epoch ends
        if epoch_avg_losses:
            # Positions at the end of each epoch
            end_positions = []
            for ep in range(cfg.epochs):
                end_positions.append((ep + 1) * len(train_dataloader))
            end_positions = end_positions[: len(epoch_avg_losses)]
            plt.plot(
                end_positions,
                epoch_avg_losses,
                marker="o",
                linestyle="--",
                label="epoch avg",
            )
        plt.xlabel("Iteration")
        plt.ylabel("Loss")
        plt.title("Training Loss (All)")
        plt.grid(True, linestyle="--", alpha=0.35)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(results_dir, "loss.png"))
        plt.close()
    except Exception as e:
        console.print(f"[yellow]Failed to render final loss plot: {e}")

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


# def evaluate():
#     cfg = TrainConfig()
#     device_obj = torch.device(device)
#     results_dir = os.path.join(cfg.save_name, "results")

#     # Prefer full-model epoch checkpoints; fall back to model.pt
#     model_path = latest_epoch_checkpoint(results_dir) or os.path.join(
#         results_dir, "model.pt"
#     )

#     # Load model if not provided
#     model = model or load_model_robust(model_path, device_obj)

#     # Determine kinds from model type
#     mode = infer_mode_from_model(model)
#     kinds = ["ast"] if mode == "ast" else ["dfg"] if mode == "dfg" else ["ast", "dfg"]

#     # Build dataloader if needed
#     if dataloader is None:
#         if isinstance(data, Dataset):
#             dataset_obj = data
#         else:
#             dataset_obj = GenericJsonDataset(
#                 paths=data,  # str path
#                 schema=SCHEMA,
#                 kinds=kinds,
#                 strict=False,
#                 debug=False,
#             )

#         dataloader = TorchDataLoader(
#             dataset_obj,
#             batch_size=32,  # vectorized; we still produce per-sample outputs
#             collate_fn=collate_multi,
#             num_workers=0,
#             pin_memory=False,
#             shuffle=False,
#         )

#     if max_samples <= 0:
#         summary = evaluate_full_dataset(
#             model=model,
#             dataloader=dataloader,
#             device=device_obj,
#             mode=mode,
#             forward_fn=forward_fn,
#         )
#     else:
#         per_sample_out = os.path.join(results_dir, "evaluation")
#         os.makedirs(per_sample_out, exist_ok=True)
#         summary = evaluate_model(
#             model=model,
#             dataloader=dataloader,
#             device=device_obj,
#             mode=mode,
#             max_samples=max_samples,
#             output_dir=per_sample_out,
#             forward_fn=forward_fn,
#         )

#     summary_file = os.path.join(results_dir, output_file)
#     with open(summary_file, "w") as f:
#         json.dump(summary, f, indent=2)

#     return summary
