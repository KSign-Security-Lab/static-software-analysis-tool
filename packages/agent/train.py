import argparse
import json
import os
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Literal, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataset.JsonDataset import JsonDataset
from model.CreativeGNN import DualStreamCrossGraphNet
from model.LateFusion import LateFusionModel
from model.SingleBranch import ASTOnlyModel, DFGOnlyModel
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from torch.utils.data import DataLoader as TorchDataLoader
from torch.utils.data import IterableDataset
from torch_geometric.data import Batch, Data
from utils.evaluate.explain import (
    compute_node_saliency,
    save_parameter_saliency_heatmaps,
    save_saliency_heatmap,
)
from utils.evaluate.metrics import (
    compute_binary_classification_metrics,
    save_epoch_metrics_and_plots,
)

# Suppress torch-scatter warning
warnings.filterwarnings("ignore", message=".*torch-scatter.*")
console = Console()


def custom_collate_fn(batch):
    """Custom collate function for PyTorch Geometric Data objects."""

    def _infer_dims(kind: str, default_x: int, default_e: int) -> tuple[int, int]:
        x_dim = None
        e_dim = None
        key = f"{kind}_graph"
        for it in batch:
            g = it.get(key)
            if g is None:
                continue
            if getattr(g, "x", None) is not None and g.x.numel() > 0:
                x_dim = g.x.size(1)
            ea = getattr(g, "edge_attr", None)
            if ea is not None:
                e_dim = ea.size(1) if ea.ndim == 2 else default_e
            if x_dim is not None and e_dim is not None:
                break
        return (x_dim or default_x, e_dim or default_e)

    ast_x_dim, ast_e_dim = _infer_dims("ast", default_x=20, default_e=1)
    dfg_x_dim, dfg_e_dim = _infer_dims("dfg", default_x=12, default_e=1)

    def _empty_graph(num_features: int, edge_dim: int) -> Data:
        return Data(
            x=torch.zeros((1, num_features), dtype=torch.float),
            edge_index=torch.zeros((2, 0), dtype=torch.long),
            edge_attr=torch.zeros((0, edge_dim), dtype=torch.float),
        )

    def _normalize_graph(g: Data, want_x: int, want_e: int) -> Data:
        x = getattr(g, "x", None)
        if x is None or x.ndim != 2 or x.size(1) != want_x:
            g.x = torch.zeros((1, want_x), dtype=torch.float)
        if getattr(g, "edge_index", None) is None:
            g.edge_index = torch.zeros((2, 0), dtype=torch.long)
        ea = getattr(g, "edge_attr", None)
        edge_index = getattr(g, "edge_index", None)
        num_edges = edge_index.size(1) if isinstance(edge_index, torch.Tensor) else 0
        if ea is None or ea.ndim != 2 or ea.size(1) != want_e:
            g.edge_attr = torch.zeros((num_edges, want_e), dtype=torch.float)
        return g

    ast_graphs = []
    dfg_graphs = []
    labels = []
    files = []
    paths = []
    ast_original_nodes = []
    ast_original_edges = []
    dfg_original_nodes = []
    dfg_original_edges = []

    for item in batch:
        ast = item.get("ast_graph")
        dfg = item.get("dfg_graph")
        lbl = item.get("label")

        if ast is None:
            ast = _empty_graph(ast_x_dim, ast_e_dim)
        else:
            ast = _normalize_graph(ast, ast_x_dim, ast_e_dim)
        if dfg is None:
            dfg = _empty_graph(dfg_x_dim, dfg_e_dim)
        else:
            dfg = _normalize_graph(dfg, dfg_x_dim, dfg_e_dim)

        if not isinstance(lbl, torch.Tensor):
            try:
                lbl = torch.tensor(int(lbl), dtype=torch.long)
            except Exception:
                lbl = torch.tensor(0, dtype=torch.long)

        ast_graphs.append(ast)
        dfg_graphs.append(dfg)
        labels.append(lbl)
        files.append(item.get("file"))
        paths.append(item.get("path"))

        # Preserve original data for human-friendly output
        ast_original_nodes.append(item.get("ast_result_original_nodes", []))
        ast_original_edges.append(item.get("ast_result_original_edges", []))
        dfg_original_nodes.append(item.get("dfg_result_original_nodes", []))
        dfg_original_edges.append(item.get("dfg_result_original_edges", []))

    # Batch the graphs using PyTorch Geometric's Batch.from_data_list
    ast_batch = Batch.from_data_list(ast_graphs)
    dfg_batch = Batch.from_data_list(dfg_graphs)

    # Stack the labels
    labels_tensor = torch.stack(labels)

    return {
        "ast_graph": ast_batch,
        "dfg_graph": dfg_batch,
        "label": labels_tensor,
        "file": files,
        "path": paths,
        "ast_result_original_nodes": ast_original_nodes,
        "ast_result_original_edges": ast_original_edges,
        "dfg_result_original_nodes": dfg_original_nodes,
        "dfg_result_original_edges": dfg_original_edges,
    }


@dataclass
class TrainConfig:
    """Training configuration with all parameters."""

    data_path: List[str] = field(
        default_factory=lambda: ["data/CWE121_full", "data/CWE122_full"]
    )
    split: str = "train"
    epochs: int = 10
    lr: float = 1e-3
    weight_decay: float = 1e-4
    device: str = "cuda:1"
    batch_size: int = 32
    num_workers: int = 0
    pin_memory: bool = False
    seed: int = 42
    hid: int = 64
    gnn_layers: int = 3
    fusion_depth: int = 2
    shuffle: bool = True
    save_name: Optional[str] = None
    mode: str = "both"
    explain: bool = False
    loss: str = "focal"
    focal_gamma: float = 2.0
    model: Literal["default", "late_fusion"] = "default"


def save_training_config(
    cfg: TrainConfig, results_dir: str, model_info: Dict[str, Any]
) -> None:
    """Save complete training configuration and model info for evaluation."""
    config = {
        "training_config": asdict(cfg),
        "model_info": model_info,
        "training_metadata": {
            "timestamp": datetime.now().isoformat(),
            "results_dir": results_dir,
            "model_weights_path": os.path.join(results_dir, "model.pt"),
        },
        "evaluation_defaults": {
            "split": "test",
            "max_samples": 1000,
            "mode": cfg.mode,
            "device": cfg.device,
        },
    }

    config_path = os.path.join(results_dir, "training_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    console.print(f"Saved training configuration → {config_path}", style="green")


def _safe_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


class FocalLoss(nn.Module):
    def __init__(
        self,
        gamma: float = 2.0,
        weight: Optional[torch.Tensor] = None,
        reduction: str = "mean",
    ) -> None:
        super().__init__()
        self.gamma = gamma
        self.reduction = reduction
        if weight is not None:
            self.register_buffer("weight", weight)

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        if self.weight is not None:
            self.weight = self.weight.to(inputs.device)
        ce_loss = F.cross_entropy(inputs, targets, weight=self.weight, reduction="none")
        pt = torch.exp(-ce_loss)
        focal_loss = (1 - pt) ** self.gamma * ce_loss
        if self.reduction == "mean":
            return focal_loss.mean()
        elif self.reduction == "sum":
            return focal_loss.sum()
        else:
            return focal_loss


def _compute_class_weights_stream(dataset: IterableDataset) -> torch.Tensor:
    """Compute class weights from streaming dataset."""
    class_counts = [0, 0]

    for sample in dataset:
        # Type guard to ensure sample is a dictionary
        if not isinstance(sample, dict):
            continue

        label = sample["label"].item()
        if 0 <= label < len(class_counts):
            class_counts[label] += 1

    # Convert to weights
    total = sum(class_counts)
    if total == 0:
        return torch.ones(2)

    weights = [
        total / (len(class_counts) * count) if count > 0 else 0
        for count in class_counts
    ]
    return torch.tensor(weights, dtype=torch.float)


def train(cfg: TrainConfig) -> str:
    """Train the model with full configuration."""

    # Set random seed
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    # Set device
    device = torch.device(cfg.device)
    console.print(f"Using device: {device}")

    # Create results directory
    results_dir = (
        f"./results/{'_'.join(cfg.data_path).replace('/', '_')}_{cfg.epochs}epochs"
    )
    if cfg.save_name:
        results_dir = f"./results/{cfg.save_name}"
    _safe_dir(results_dir)

    # Create dataset using local JsonDataset (expects cfg.data_path as a path)
    console.print(f"Loading dataset from path: {cfg.data_path}")
    dataset = JsonDataset(paths=cfg.data_path)

    # Compute class weights (non-streaming path)
    console.print("Computing class weights...")
    if isinstance(dataset, IterableDataset):
        class_weights = _compute_class_weights_stream(dataset)
    else:
        counts = [0, 0]
        for item in dataset:
            lbl = item.get("label")
            if isinstance(lbl, torch.Tensor):
                v = int(lbl.item())
            else:
                try:
                    v = int(lbl) if lbl is not None else 0
                except Exception:
                    v = 0
            if 0 <= v < 2:
                counts[v] += 1
        total = sum(counts) or 1
        # Use sqrt to reduce the extreme imbalance impact
        weights = [total / (len(counts) * (c**0.5)) if c > 0 else 0 for c in counts]
        # Normalize weights to sum to number of classes
        weight_sum = sum(weights)
        if weight_sum > 0:
            weights = [w * len(counts) / weight_sum for w in weights]
        class_weights = torch.tensor(weights, dtype=torch.float)
    console.print(f"Class weights: {class_weights}")

    # Create dataloader
    dataloader = TorchDataLoader(
        dataset,
        batch_size=cfg.batch_size,
        num_workers=cfg.num_workers,
        pin_memory=cfg.pin_memory,
        collate_fn=custom_collate_fn,
        shuffle=cfg.shuffle,
    )

    # Create model
    if cfg.mode == "ast":
        model = ASTOnlyModel(
            ast_in=20,
            ast_edge_dim=1,
            hid=cfg.hid,
            out_classes=2,
            gnn_layers=cfg.gnn_layers,
        )
    elif cfg.mode == "dfg":
        model = DFGOnlyModel(
            dfg_in=12,
            dfg_edge_dim=1,
            hid=cfg.hid,
            out_classes=2,
            gnn_layers=cfg.gnn_layers,
        )
    elif cfg.model == "late_fusion":
        model = LateFusionModel(
            ast_in=20,
            ast_edge_dim=1,
            dfg_in=12,
            dfg_edge_dim=1,
        )
    else:  # default
        model = DualStreamCrossGraphNet(
            ast_in=20,
            ast_edge=1,
            dfg_in=12,
            dfg_edge=1,
            hid=cfg.hid,
            out_classes=2,
            gnn_layers=cfg.gnn_layers,
            fusion_depth=cfg.fusion_depth,
            use_ast=True,
            use_dfg=True,
        )

    model.to(device)
    console.print(f"Model created: {cfg.mode} mode")

    # Create optimizer and loss
    optimizer = torch.optim.Adam(
        model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
    )

    if cfg.loss == "focal":
        criterion = FocalLoss(gamma=cfg.focal_gamma, weight=class_weights.to(device))
    else:
        criterion = nn.CrossEntropyLoss(weight=class_weights.to(device))

        # Training loop
    console.print(f"Starting training for {cfg.epochs} epochs...")

    # Initialize variables for final stats
    avg_loss = 0.0
    metrics = {"accuracy": 0.0}
    samples_processed = 0

    for epoch in range(cfg.epochs):
        model.train()
        total_loss = 0
        all_predictions = []
        all_probabilities = []
        all_labels = []
        samples_processed = 0

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(f"Epoch {epoch+1}/{cfg.epochs}", total=None)

            for batch_idx, batch in enumerate(dataloader):
                optimizer.zero_grad()

                # Move data to device
                ast_data = batch["ast_graph"].to(device)
                dfg_data = batch["dfg_graph"].to(device)
                labels = batch["label"].to(device)

                # Forward pass
                if cfg.mode == "ast":
                    logits = model(ast_data)
                elif cfg.mode == "dfg":
                    logits = model(dfg_data)
                else:  # both
                    logits = model(ast_data, dfg_data)

                # Compute loss
                loss = criterion(logits, labels.squeeze())

                # Backward pass
                loss.backward()
                optimizer.step()

                total_loss += loss.item()

                # Store predictions for metrics
                with torch.no_grad():
                    probs = F.softmax(logits, dim=-1)
                    predictions = probs.argmax(dim=-1)
                    # Store probabilities for positive class (class 1)
                    positive_probs = probs[:, 1].cpu().numpy()
                    all_predictions.extend(predictions.cpu().numpy())
                    all_probabilities.extend(positive_probs)
                    all_labels.extend(labels.squeeze().cpu().numpy())
                    samples_processed += len(labels)

                progress.update(task, advance=1)

                # Generate saliency if requested (last batch of epoch)
                if cfg.explain and batch_idx == 0:
                    try:
                        with torch.no_grad():
                            if cfg.mode == "ast":
                                node_saliency, param_saliency = compute_node_saliency(
                                    model, ast_data, None, positive_class=1
                                )
                                save_saliency_heatmap(
                                    results_dir,
                                    f"epoch_{epoch+1}_ast_saliency",
                                    node_saliency["ast"],
                                )
                            elif cfg.mode == "dfg":
                                node_saliency, param_saliency = compute_node_saliency(
                                    model, None, dfg_data, positive_class=1
                                )
                                save_saliency_heatmap(
                                    results_dir,
                                    f"epoch_{epoch+1}_dfg_saliency",
                                    node_saliency["dfg"],
                                )
                            else:  # both
                                node_saliency, param_saliency = compute_node_saliency(
                                    model, ast_data, dfg_data, positive_class=1
                                )
                                save_saliency_heatmap(
                                    results_dir,
                                    f"epoch_{epoch+1}_ast_saliency",
                                    node_saliency["ast"],
                                )
                                save_saliency_heatmap(
                                    results_dir,
                                    f"epoch_{epoch+1}_dfg_saliency",
                                    node_saliency["dfg"],
                                )

                            save_parameter_saliency_heatmaps(
                                results_dir,
                                param_saliency,
                                top_k=8,
                            )
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Could not generate saliency: {e}[/yellow]"
                        )

        # Compute metrics
        metrics = compute_binary_classification_metrics(all_labels, all_probabilities)
        avg_loss = total_loss / samples_processed if samples_processed > 0 else 0.0

        # Handle cases where metrics might be None
        accuracy_str = (
            f"{metrics['accuracy']:.4f}" if metrics["accuracy"] is not None else "N/A"
        )
        console.print(
            f"Epoch {epoch+1}/{cfg.epochs} - Loss: {avg_loss:.4f}, Accuracy: {accuracy_str}"
        )

        # Save epoch metrics
        save_epoch_metrics_and_plots(
            results_dir,
            epoch + 1,
            all_labels,
            all_probabilities,
            metrics,
        )

    # Save final weights
    weights_path = f"{results_dir}/model.pt"
    torch.save(model.state_dict(), weights_path)
    console.print(f"Saved model weights → {weights_path}", style="green")

    # Save training configuration for evaluation
    model_info = {
        "model_type": cfg.mode,
        "model_class": model.__class__.__name__,
        "input_dimensions": {
            "ast_in": 2,
            "ast_edge_dim": 1,
            "dfg_in": 2,
            "dfg_edge_dim": 1,
        },
        "architecture": {
            "hid": cfg.hid,
            "out_classes": 2,
            "gnn_layers": cfg.gnn_layers,
        },
        "training_stats": {
            "total_epochs": cfg.epochs,
            "final_loss": avg_loss,
            "final_accuracy": metrics.get("accuracy", 0.0),
            "samples_processed": samples_processed,
        },
    }

    save_training_config(cfg, results_dir, model_info)

    console.print(
        "[cyan]Use 'python evaluate_simple.py --results_dir {}' to evaluate the trained model[/cyan]".format(
            results_dir
        )
    )

    return results_dir


def main() -> None:
    """Main function with minimal argument parser that only overrides provided args."""
    # Default configuration - modify these for advanced usage
    cfg = TrainConfig()

    # Parse only minimal arguments
    parser = argparse.ArgumentParser(description="Train GNN model")
    parser.add_argument("--epochs", type=int, help="Number of epochs")
    parser.add_argument("--lr", type=float, help="Learning rate")
    parser.add_argument("--device", type=str, help="Device to use")
    parser.add_argument("--batch_size", type=int, help="Batch size")
    parser.add_argument(
        "--mode", type=str, choices=["both", "ast", "dfg"], help="Model mode"
    )

    args = parser.parse_args()

    # Only override parameters that were explicitly provided
    if args.epochs is not None:
        cfg.epochs = args.epochs
    if args.lr is not None:
        cfg.lr = args.lr
    if args.device is not None:
        cfg.device = args.device
    if args.batch_size is not None:
        cfg.batch_size = args.batch_size
    if args.mode is not None:
        cfg.mode = args.mode

    train(cfg)


if __name__ == "__main__":
    main()
