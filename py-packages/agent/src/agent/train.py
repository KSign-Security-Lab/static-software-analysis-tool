import argparse
import json
import os
import warnings
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Protocol,
    TypeVar,
    TypedDict,
    NotRequired,
)
import torch
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from torch.utils.data import (
    DataLoader as TorchDataLoader,
    Dataset as TorchDataset,
)
from torch_geometric.data import Batch
from torch_geometric.data import Data as PyGData
from .model.CreativeGNN import DualStreamCrossGraphNet
from .model.LateFusion import LateFusionModel
from .model.SingleBranch import ASTOnlyModel, DFGOnlyModel
from .config import Schema, TrainConfig
from .dataset.JsonDataset import GenericJsonDataset, AnyGraphModel, juliet_json_to_sample


# Suppress torch-scatter warning noise
warnings.filterwarnings("ignore", message=".*torch-scatter.*")
console = Console()


ForwardFn = Callable[[torch.nn.Module, Dict[str, Any], torch.device, str], torch.Tensor]


# ===== Typing: sample and dataset protocol =====
T_co = TypeVar("T_co", covariant=True)


class Sample(TypedDict, total=False):
    """
    Per-item sample returned by __getitem__ for training.
    'y' is required to silence 'TypedDict not required' errors.
    Other keys remain optional.
    """

    y: torch.Tensor
    ast_graph: NotRequired[Any]
    dfg_graph: NotRequired[Any]
    # add other optional fields you collate if needed


class SupportsIndex(Protocol[T_co]):
    """
    Structural protocol for indexable & sized datasets.
    Use 'idx: Any' to align with PyTorch stubs where __getitem__ often
    uses an untyped 'idx' parameter, which avoids Pyright incompatibility.
    """

    def __len__(self) -> int: ...
    def __getitem__(self, idx: Any) -> T_co: ...


def select_model(
    cfg: TrainConfig,
    ast_in: int,
    dfg_in: int,
    edge_dim_ast: int,
    edge_dim_dfg: int,
) -> torch.nn.Module:
    if cfg.mode == "ast":
        return ASTOnlyModel(
            ast_in=ast_in,
            ast_edge_dim=edge_dim_ast,
            hid=cfg.hid,
            out_classes=cfg.out_classes,
            gnn_layers=cfg.gnn_layers,
        )
    if cfg.mode == "dfg":
        return DFGOnlyModel(
            dfg_in=dfg_in,
            dfg_edge_dim=edge_dim_dfg,
            hid=cfg.hid,
            out_classes=cfg.out_classes,
            gnn_layers=cfg.gnn_layers,
        )
    if cfg.mode == "late_fusion":
        return LateFusionModel(
            ast_in=ast_in,
            ast_edge_dim=edge_dim_ast,
            dfg_in=dfg_in,
            dfg_edge_dim=edge_dim_dfg,
            hid=cfg.hid,
            out_classes=cfg.out_classes,
            gnn_layers=cfg.gnn_layers,
            fusion_depth=cfg.fusion_depth,
            use_ast=True,
            use_dfg=True,
        )
    if cfg.mode == "both":
        return DualStreamCrossGraphNet(
            ast_in=ast_in,
            ast_edge=edge_dim_ast,
            dfg_in=dfg_in,
            dfg_edge=edge_dim_dfg,
            hid=cfg.hid,
            out_classes=cfg.out_classes,
            gnn_layers=cfg.gnn_layers,
            fusion_depth=cfg.fusion_depth,
            use_ast=True,
            use_dfg=True,
        )
    raise ValueError(f"Invalid mode: {cfg.mode}")


def _harmonize_graph_dims(graphs: List[PyGData]) -> List[PyGData]:
    """Pad/align node and edge features across a list of graphs by name.

    Uses `x_feature_names` and `edge_feature_names` if present; otherwise aligns
    by raw feature dimension (no-op if equal).
    """
    if not graphs:
        return graphs

    # Collect union of x feature names
    name_sets = [getattr(g, "x_feature_names", None) for g in graphs]
    if any(ns is None for ns in name_sets):
        # fallback: try to ensure same dim; if not equal, pad to max dim
        max_x = max(int(g.x.size(1)) if hasattr(g, "x") and g.x is not None else 0 for g in graphs)
        out = []
        for g in graphs:
            if hasattr(g, "x") and g.x is not None and g.x.size(1) < max_x:
                pad = torch.zeros((g.x.size(0), max_x - g.x.size(1)), dtype=g.x.dtype, device=g.x.device)
                x = torch.cat([g.x, pad], dim=1)
                g = g.clone()
                g.x = x
            out.append(g)
        # Edge attrs similar
        max_e = max(int(g.edge_attr.size(1)) if hasattr(g, "edge_attr") and g.edge_attr is not None else 0 for g in graphs)
        out2 = []
        for g in out:
            if hasattr(g, "edge_attr") and g.edge_attr is not None and g.edge_attr.size(1) < max_e:
                pad = torch.zeros((g.edge_attr.size(0), max_e - g.edge_attr.size(1)), dtype=g.edge_attr.dtype, device=g.edge_attr.device)
                gg = g.clone()
                gg.edge_attr = torch.cat([g.edge_attr, pad], dim=1)
                out2.append(gg)
            else:
                out2.append(g)
        return out2

    # Named alignment
    union_x_names: List[str] = []
    seen = set()
    for ns in name_sets:
        for n in ns or []:
            if n not in seen:
                union_x_names.append(n); seen.add(n)

    # Edge feature names union
    e_seen = set()
    union_e_names: List[str] = []
    for g in graphs:
        names = getattr(g, "edge_feature_names", None) or []
        for n in names:
            if n not in e_seen:
                union_e_names.append(n); e_seen.add(n)

    aligned: List[PyGData] = []
    for g in graphs:
        gg = g.clone()
        # Align x
        x_names = getattr(g, "x_feature_names", [])
        if gg.x is None:
            gg.x = torch.zeros((0, len(union_x_names)), dtype=torch.float)
        else:
            cols = {name: i for i, name in enumerate(x_names)}
            new_x = torch.zeros((gg.x.size(0), len(union_x_names)), dtype=gg.x.dtype)
            for j, name in enumerate(union_x_names):
                if name in cols:
                    new_x[:, j] = gg.x[:, cols[name]]
            gg.x = new_x
            gg.x_feature_names = union_x_names

        # Align edge_attr
        e_names = getattr(g, "edge_feature_names", [])
        if getattr(gg, "edge_attr", None) is None or gg.edge_attr.numel() == 0:
            gg.edge_attr = torch.zeros((gg.edge_index.size(1), len(union_e_names)), dtype=torch.float)
        else:
            ecols = {name: i for i, name in enumerate(e_names)}
            new_e = torch.zeros((gg.edge_attr.size(0), len(union_e_names)), dtype=gg.edge_attr.dtype)
            for j, name in enumerate(union_e_names):
                if name in ecols:
                    new_e[:, j] = gg.edge_attr[:, ecols[name]]
            gg.edge_attr = new_e
            gg.edge_feature_names = union_e_names

        aligned.append(gg)
    return aligned


def collate_multi(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Collect labels robustly; default to 0 if missing
    ys: List[torch.Tensor] = []
    for it in batch:
        try:
            y_val = it["y"] if isinstance(it, dict) else getattr(it, "y")
        except Exception:
            y_val = None
        if y_val is None:
            y_t = torch.tensor(0, dtype=torch.long)
        elif isinstance(y_val, torch.Tensor):
            y_t = y_val.to(dtype=torch.long)
        else:
            y_t = torch.tensor(int(y_val), dtype=torch.long)
        ys.append(y_t)
    out: Dict[str, Any] = {"y": torch.stack(ys)}

    # Union of *_graph keys across all items
    graph_keys: List[str] = []
    seen: set[str] = set()
    for it in batch:
        keys = it.keys() if isinstance(it, dict) else list(getattr(it, "keys")() or [])
        for k in keys:
            if isinstance(k, str) and k.endswith("_graph") and k not in seen:
                graph_keys.append(k)
                seen.add(k)

    def _empty_graph_placeholder() -> PyGData:
        return PyGData(
            x=torch.zeros((1, 0), dtype=torch.float),
            edge_index=torch.zeros((2, 0), dtype=torch.long),
            edge_attr=torch.zeros((0, 1), dtype=torch.float),
        )

    for k in graph_keys:
        graphs: List[PyGData] = []
        for it in batch:
            g = None
            if isinstance(it, dict):
                g = it.get(k)
            else:
                try:
                    g = getattr(it, k)
                except Exception:
                    g = None
            graphs.append(g if isinstance(g, PyGData) else _empty_graph_placeholder())
        graphs = _harmonize_graph_dims(graphs)
        out[k] = Batch.from_data_list(graphs)

    # Pass through union of non-graph, non-label metadata as lists
    meta_keys: List[str] = []
    seen_meta: set[str] = set()
    for it in batch:
        keys = it.keys() if isinstance(it, dict) else list(getattr(it, "keys")() or [])
        for k in keys:
            if k == "y" or (isinstance(k, str) and k.endswith("_graph")):
                continue
            if k not in seen_meta:
                seen_meta.add(k)
                meta_keys.append(k)
    for k in meta_keys:
        out[k] = [
            (it.get(k) if isinstance(it, dict) else getattr(it, k, None)) for it in batch
        ]
    return out


def _get_from_item(item: Any, key: str, default: Any = None) -> Any:
    """Safely get attribute/key from dict-like or Data-like objects."""
    if isinstance(item, dict):
        return item.get(key, default)
    # torch_geometric.data.Data supports attribute access
    try:
        return getattr(item, key)
    except Exception:
        return default


def infer_dims_from_dataset(
    dataset: SupportsIndex[Sample], kinds: List[str]
) -> Dict[str, Tuple[int, int]]:
    """Inspect a few samples to infer x and edge_attr dims per kind.

    Returns mapping: kind -> (x_dim, e_dim)
    """
    dims: Dict[str, Tuple[int, int]] = {}
    sample_indices = [0]
    if len(dataset) > 1:
        sample_indices.append(len(dataset) - 1)
    for k in kinds:
        x_dim = 0
        e_dim = 0
        for idx in sample_indices:
            item = dataset[idx]
            g = _get_from_item(item, f"{k}_graph")
            if g is None:
                continue
            if hasattr(g, "x") and g.x is not None and g.x.dim() == 2:
                x_dim = max(x_dim, int(g.x.size(1)))
            edge_attr = getattr(g, "edge_attr", None)
            if isinstance(edge_attr, torch.Tensor) and edge_attr.dim() == 2:
                e_dim = max(e_dim, int(edge_attr.size(1)))
        dims[k] = (x_dim, e_dim)
    return dims


def save_training_config(
    cfg: TrainConfig, results_dir: str, model_info: Dict[str, Any]
) -> None:
    # Support both dataclasses and Pydantic BaseModel configs
    if hasattr(cfg, "model_dump"):
        cfg_dict = cfg.model_dump()  # type: ignore[attr-defined]
    elif is_dataclass(cfg):
        cfg_dict = asdict(cfg)
    else:
        # best-effort fallback
        cfg_dict = dict(vars(cfg))

    config = {
        "training_config": cfg_dict,
        "model_info": model_info,
        "training_metadata": {
            "timestamp": datetime.now().isoformat(),
            "results_dir": results_dir,
            "model_weights_path": os.path.join(results_dir, "model.pt"),
        },
    }
    config_path = os.path.join(results_dir, "training_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    console.print(f"Saved training configuration → {config_path}", style="green")


def compute_class_weights(
    indices: List[int], dataset: SupportsIndex[Sample], num_classes: int = 2
) -> torch.Tensor:
    counts = [0] * num_classes
    for idx in indices:
        item = dataset[idx]
        y_val = _get_from_item(item, "y", None)
        if y_val is None:
            continue
        y = int(y_val.item() if hasattr(y_val, "item") else y_val)
        if 0 <= y < num_classes:
            counts[y] += 1
    total = sum(counts)
    if total == 0:
        return torch.ones(num_classes, dtype=torch.float)
    # Smooth with sqrt to avoid extreme imbalance spikes
    weights = [total / (num_classes * (c**0.5)) if c > 0 else 0.0 for c in counts]
    s = sum(weights)
    if s > 0:
        weights = [w * num_classes / s for w in weights]
    else:
        weights = [1.0] * num_classes
    return torch.tensor(weights, dtype=torch.float)


def forward_by_mode(
    model: torch.nn.Module, batch: Dict[str, Any], device: torch.device, mode: str
) -> torch.Tensor:
    """Default forward that routes by mode using keys in the collated batch."""
    if mode == "ast":
        return model(batch["ast_graph"].to(device))
    if mode == "dfg":
        return model(batch["dfg_graph"].to(device))
    # both or late_fusion default to two-stream
    return model(batch["ast_graph"].to(device), batch["dfg_graph"].to(device))


def build_dataloader(
    dataset: TorchDataset[Sample],
    cfg: "TrainConfig",
    *,
    collate_fn: Optional[Callable[[List[Any]], Any]] = None,
) -> TorchDataLoader:
    return TorchDataLoader(
        dataset,
        batch_size=cfg.batch_size,
        num_workers=cfg.num_workers,
        pin_memory=cfg.pin_memory,
        shuffle=cfg.shuffle,
        collate_fn=collate_fn or collate_multi,
    )


# build_datasets_and_stats was removed as overengineering; kept logic local to entrypoint


def train_model_from_dataset(
    cfg: TrainConfig,
    dataloader: TorchDataLoader,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    criterion: torch.nn.Module,
    device: torch.device,
    local_forward: ForwardFn,
    iter_losses: List[float],
    epoch_avg_losses: List[float],
    results_dir: str,
):
    for epoch in range(cfg.epochs):
        model.train()
        running_loss = 0.0
        num_batches = 0
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(
                f"Epoch {epoch+1}/{cfg.epochs}", total=len(dataloader)
            )
            for batch in dataloader:
                optimizer.zero_grad()

                labels = batch["y"].to(device)

                logits = local_forward(model, batch, device, cfg.mode)

                loss = criterion(logits, labels)
                loss.backward()
                optimizer.step()

                # track loss per iteration and update plot
                curr_loss = float(loss.item())
                iter_losses.append(curr_loss)
                running_loss += curr_loss
                num_batches += 1

                # update progress description with current loss
                progress.update(
                    task,
                    advance=1,
                    description=f"Epoch {epoch+1}/{cfg.epochs} | loss={curr_loss:.6f}",
                )

        # epoch summary
        if num_batches > 0:
            avg_loss = running_loss / num_batches
            epoch_avg_losses.append(avg_loss)
            console.print(f"Epoch {epoch+1} average loss: {avg_loss:.6f}")

        # keep epoch checkpoints (full model for backward compatibility)
        torch.save(model, os.path.join(results_dir, f"model_epoch_{epoch+1}.pt"))
