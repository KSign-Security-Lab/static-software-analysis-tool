import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from datasets import load_dataset
from explain import (
    compute_node_saliency,
    save_parameter_saliency_heatmaps,
    save_saliency_heatmap,
)
from metrics import compute_binary_classification_metrics, save_epoch_metrics_and_plots
from model.CreativeGNN import DualStreamCrossGraphNet
from model.LateFusion import LateFusionModel  # assumes present on PYTHONPATH
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
from torch.utils.data import IterableDataset, get_worker_info
from torch_geometric.data import Data

console = Console()


DEFAULT_WEIGHT_MAX_SAMPLES = 4096


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
        else:
            self.weight = None

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        target = target.view(-1).long()
        log_probs = F.log_softmax(logits, dim=1)
        probs = log_probs.exp()
        idx = torch.arange(target.size(0), device=logits.device)
        pt = probs[idx, target]
        focal_factor = (1 - pt).pow(self.gamma)
        loss = -focal_factor * log_probs[idx, target]
        weight = getattr(self, "weight", None)
        if weight is not None:
            loss = loss * weight[target]
        if self.reduction == "mean":
            return loss.mean()
        if self.reduction == "sum":
            return loss.sum()
        return loss


@dataclass
class TrainConfig:
    repo_id: str
    split: str
    epochs: int
    lr: float
    weight_decay: float
    device: str
    batch_size: int
    num_workers: int
    pin_memory: bool
    seed: int
    hid: int
    gnn_layers: int
    fusion_depth: int
    shuffle_buffer: int
    save_name: Optional[str]
    mode: str  # "both" | "ast" | "dfg"
    explain: bool  # run saliency after evaluation each epoch
    loss: str
    focal_gamma: float
    model: str


def _build_pyg_from_ast_item(ast_item: Dict[str, Any]) -> Data:
    """Build a PyG Data from an AST graph dict with keys: nodes, edges_ast_pc."""
    nodes = ast_item.get("nodes", [])
    if not nodes:
        x = torch.zeros((1, 2), dtype=torch.float)
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, 1), dtype=torch.float)
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

    sid_to_row: Dict[int, int] = {}
    feats: List[List[float]] = []
    for i, n in enumerate(nodes):
        sid = int(n.get("sid", i))
        sid_to_row[sid] = i
        f = n.get("feat", {})
        feats.append([float(f.get("node_type_id", 0.0)), float(f.get("in_loop", 0.0))])
    x = torch.tensor(feats, dtype=torch.float)

    pc = ast_item.get("edges_ast_pc", [])
    ei_list: List[List[int]] = []
    ea_list: List[List[float]] = []
    for u, v, t in pc:
        u, v = int(u), int(v)
        if u in sid_to_row and v in sid_to_row:
            ei_list.append([sid_to_row[u], sid_to_row[v]])
            ea_list.append([float(t)])
    if ei_list:
        edge_index = torch.tensor(np.array(ei_list).T, dtype=torch.long)
        edge_attr = torch.tensor(ea_list, dtype=torch.float)
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, 1), dtype=torch.float)
    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)


def _build_pyg_from_dfg_item(dfg_item: Dict[str, Any]) -> Data:
    """Build a PyG Data from a DFG graph dict with keys: nodes, edges."""
    nodes = dfg_item.get("nodes", [])
    if not nodes:
        x = torch.zeros((1, 4), dtype=torch.float)
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, 1), dtype=torch.float)
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

    id_to_row: Dict[int, int] = {}
    feats: List[List[float]] = []
    for i, n in enumerate(nodes):
        nid = int(n.get("id", i))
        id_to_row[nid] = i
        f = n.get("features", {})
        feats.append(
            [
                float(f.get("inDegreeDFG", 0)),
                float(f.get("outDegreeDFG", 0)),
                float(f.get("defCount", 0)),
                float(f.get("useCount", 0)),
            ]
        )
    x = torch.tensor(feats, dtype=torch.float)

    edges = dfg_item.get("edges", [])
    ei_list: List[List[int]] = []
    ea_list: List[List[float]] = []
    for e in edges:
        su = int(e.get("source", -1))
        sv = int(e.get("destination", -1))
        if su in id_to_row and sv in id_to_row:
            ei_list.append([id_to_row[su], id_to_row[sv]])
            ea_list.append([1.0])
    if ei_list:
        edge_index = torch.tensor(np.array(ei_list).T, dtype=torch.long)
        edge_attr = torch.tensor(ea_list, dtype=torch.float)
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, 1), dtype=torch.float)
    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)


def _coerce_label(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        vi = int(v)
        return vi if vi in (0, 1) else None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "t", "yes", "y", "bad", "vulnerable"):
            return 1
        if s in ("0", "false", "f", "no", "n", "good", "safe"):
            return 0
    return None


class HFStreamingGraphs(IterableDataset):
    """
    Wrap a Hugging Face streaming dataset and shard per DataLoader worker.
    Each item is a python dict: {"ast_graph": <dict>, "dfg_graph": <dict>, "label": torch.LongTensor([0 or 1])}
    """

    def __init__(self, repo_id: str, split: str, shuffle_buffer: int, seed: int):
        super().__init__()
        self.repo_id = repo_id
        self.split = split
        self.shuffle_buffer = shuffle_buffer
        self.seed = seed

    def _base_stream(self):
        ds = load_dataset(self.repo_id, split=self.split, streaming=True)
        # buffer shuffle for better stochasticity
        if hasattr(ds, "shuffle"):
            return ds.shuffle(seed=self.seed)
        else:
            raise ValueError(f"Unsupported dataset type: {type(ds)}")

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        info = get_worker_info()
        stream = self._base_stream()
        if (
            info is not None
            and hasattr(stream, "shard")
            and callable(getattr(stream, "shard", None))
        ):
            # shard across workers for parallel I/O
            stream = stream.shard(num_shards=info.num_workers, index=info.id)

        for ex in stream:
            # expect fields: "ast_result", "dfg_result", "label"
            if not isinstance(ex, dict):
                continue
            lab = _coerce_label(ex.get("label", None))
            if lab is None:
                continue
            ast_g = ex.get("ast_result", None)
            dfg_g = ex.get("dfg_result", None)

            # Parse JSON strings if they are strings
            if isinstance(ast_g, str):
                try:
                    ast_g = json.loads(ast_g)
                except json.JSONDecodeError:
                    continue
            if isinstance(dfg_g, str):
                try:
                    dfg_g = json.loads(dfg_g)
                except json.JSONDecodeError:
                    continue

            if not isinstance(ast_g, dict) or not isinstance(dfg_g, dict):
                continue
            yield {
                "ast_graph": ast_g,
                "dfg_graph": dfg_g,
                "label": torch.tensor(lab, dtype=torch.long),
            }


def _collate_list(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Simple list-collate; we’ll loop over items inside the training step.
    return {
        "ast_graph": [b["ast_graph"] for b in batch],
        "dfg_graph": [b["dfg_graph"] for b in batch],
        "label": [b["label"] for b in batch],
    }


def _build_dummy_pyg_graph() -> Data:
    x = torch.zeros((1, 1), dtype=torch.float)
    edge_index = torch.zeros((2, 0), dtype=torch.long)
    return Data(x=x, edge_index=edge_index)


def _infer_dims_from_sample(
    sample: Dict[str, Any], mode: str
) -> Tuple[int, int, int, int]:
    if mode == "ast":
        ast_data = _build_pyg_from_ast_item(sample["ast_graph"])
        dfg_data = _build_dummy_pyg_graph()
    elif mode == "dfg":
        ast_data = _build_dummy_pyg_graph()
        dfg_data = _build_pyg_from_dfg_item(sample["dfg_graph"])
    else:
        ast_data = _build_pyg_from_ast_item(sample["ast_graph"])
        dfg_data = _build_pyg_from_dfg_item(sample["dfg_graph"])
    ast_in = int(ast_data.x.size(1))
    ast_edge_attr = getattr(ast_data, "edge_attr", None)
    ast_edge = 0
    if (
        ast_edge_attr is not None
        and hasattr(ast_edge_attr, "size")
        and ast_edge_attr.numel() > 0
    ):
        try:
            ast_edge = int(ast_edge_attr.size(1))
        except (AttributeError, IndexError):
            ast_edge = 0

    dfg_in = int(dfg_data.x.size(1))
    dfg_edge_attr = getattr(dfg_data, "edge_attr", None)
    dfg_edge = 0
    if (
        dfg_edge_attr is not None
        and hasattr(dfg_edge_attr, "size")
        and dfg_edge_attr.numel() > 0
    ):
        try:
            dfg_edge = int(dfg_edge_attr.size(1))
        except (AttributeError, IndexError):
            dfg_edge = 0
    return max(1, ast_in), max(1, ast_edge), max(1, dfg_in), max(1, dfg_edge)


def _compute_class_weights_stream(
    stream: Iterable[Dict[str, Any]],
    device: torch.device,
    max_samples: Optional[int] = None,
) -> torch.Tensor:
    """One-pass estimate over a limited subset of the stream if requested."""
    pos = neg = 0
    for i, ex in enumerate(stream):
        y = int(ex["label"].item())
        if y == 1:
            pos += 1
        else:
            neg += 1
        if max_samples is not None and (i + 1) >= max_samples:
            break
    if pos == 0 or neg == 0:
        return torch.tensor([1.0, 1.0], dtype=torch.float, device=device)
    pos_w = neg / max(pos, 1)
    return torch.tensor([1.0, pos_w], dtype=torch.float, device=device)


def _safe_len(obj: Iterable[Any]) -> Optional[int]:
    try:
        return int(len(obj))
    except TypeError:
        return None


def train(cfg: TrainConfig) -> str:
    # Seeds
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    # Build dataset + loader
    ds = HFStreamingGraphs(cfg.repo_id, cfg.split, cfg.shuffle_buffer, cfg.seed)
    loader = TorchDataLoader(
        ds,
        batch_size=cfg.batch_size,
        num_workers=cfg.num_workers,
        pin_memory=cfg.pin_memory,
        collate_fn=_collate_list,
    )

    # Bootstrap a single sample to infer dims and init model
    first_batch = next(iter(loader))
    first_sample = {
        "ast_graph": first_batch["ast_graph"][0],
        "dfg_graph": first_batch["dfg_graph"][0],
        "label": first_batch["label"][0],
    }
    ast_in, ast_edge, dfg_in, dfg_edge = _infer_dims_from_sample(first_sample, cfg.mode)

    device = torch.device(cfg.device)
    use_ast = cfg.mode in ("both", "ast")
    use_dfg = cfg.mode in ("both", "dfg")

    if cfg.model == "gnn":
        model = DualStreamCrossGraphNet(
            ast_in,
            ast_edge,
            dfg_in,
            dfg_edge,
            hid=cfg.hid,
            out_classes=2,
            gnn_layers=cfg.gnn_layers,
            fusion_depth=cfg.fusion_depth,
            use_ast=use_ast,
            use_dfg=use_dfg,
        ).to(device)
    else:
        if cfg.mode == "ast":
            model = ASTOnlyModel(
                ast_in, ast_edge, hid=cfg.hid, out_classes=2, gnn_layers=cfg.gnn_layers
            ).to(device)
        elif cfg.mode == "dfg":
            model = DFGOnlyModel(
                dfg_in, dfg_edge, hid=cfg.hid, out_classes=2, gnn_layers=cfg.gnn_layers
            ).to(device)
        else:
            model = LateFusionModel(
                ast_in,
                ast_edge,
                dfg_in,
                dfg_edge,
                hid=cfg.hid,
                out_classes=2,
                gnn_layers=cfg.gnn_layers,
                fusion_depth=cfg.fusion_depth,
                use_ast=True,
                use_dfg=True,
            ).to(device)

    # Rebuild a **fresh** loader so the first sample isn't lost
    ds2 = HFStreamingGraphs(cfg.repo_id, cfg.split, cfg.shuffle_buffer, cfg.seed)
    loader = TorchDataLoader(
        ds2,
        batch_size=cfg.batch_size,
        num_workers=cfg.num_workers,
        pin_memory=cfg.pin_memory,
        collate_fn=_collate_list,
    )

    # Estimate class weights over a limited pass
    ds_for_weights = HFStreamingGraphs(
        cfg.repo_id, cfg.split, cfg.shuffle_buffer, cfg.seed
    )
    cw_loader = TorchDataLoader(
        ds_for_weights, batch_size=1, num_workers=0, collate_fn=_collate_list
    )
    console.print("[yellow]Computing class weights...[/yellow]")
    max_weight_samples = _safe_len(cw_loader)
    if max_weight_samples is None:
        max_weight_samples = DEFAULT_WEIGHT_MAX_SAMPLES
    class_weights = _compute_class_weights_stream(
        ({"label": b["label"][0]} for b in cw_loader),
        device,
        max_samples=max_weight_samples,
    )
    weights_info = class_weights.detach().cpu().numpy().tolist()
    if cfg.loss == "focal":
        criterion = FocalLoss(gamma=cfg.focal_gamma, weight=class_weights)
    else:
        criterion = nn.CrossEntropyLoss(weight=class_weights)
    criterion = criterion.to(device)
    if cfg.loss == "focal":
        console.print(
            f"[yellow]Loss: focal (gamma={cfg.focal_gamma}) with class weights {weights_info}[/yellow]"
        )
    else:
        console.print(
            f"[yellow]Loss: weighted cross entropy with class weights {weights_info}[/yellow]"
        )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
    )

    console.print(
        f"[blue]Model: {cfg.model} • mode={cfg.mode} • hid={cfg.hid} • layers={cfg.gnn_layers}[/blue]"
    )

    # Results dir
    from datetime import datetime

    run_name = cfg.save_name or datetime.now().strftime("%y%m%d-%H%M%S")
    import os

    results_dir = os.path.join(os.getcwd(), "result", run_name)
    os.makedirs(results_dir, exist_ok=True)

    console.rule("[bold green]Training")
    progress_columns = (
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("• loss={task.fields[loss]:.4f} acc={task.fields[acc]:.3f}"),
    )

    with Progress(*progress_columns, console=console) as progress:
        epoch_task = progress.add_task("Epochs", total=cfg.epochs, loss=0.0, acc=0.0)
        for ep in range(1, cfg.epochs + 1):
            model.train()
            total_loss = 0.0
            total_correct = 0
            total = 0
            batch_count = 0
            # buffers for evaluation
            eval_labels: List[int] = []
            eval_probs: List[float] = []
            batch_total = _safe_len(loader)
            batch_task = progress.add_task(
                f"Epoch {ep}", total=batch_total, loss=0.0, acc=0.0
            )

            last_batch = None
            last_B = 0
            for batch in loader:
                B = len(batch["label"])
                batch_count += 1
                last_batch = batch
                last_B = B

                for i in range(B):
                    y = batch["label"][i].unsqueeze(0).to(device)

                    ast_item = batch["ast_graph"][i]
                    dfg_item = batch["dfg_graph"][i]

                    optimizer.zero_grad(set_to_none=True)
                    if cfg.mode == "ast":
                        ast_data = _build_pyg_from_ast_item(ast_item).to(str(device))
                        out = model(ast_data)
                    elif cfg.mode == "dfg":
                        dfg_data = _build_pyg_from_dfg_item(dfg_item).to(str(device))
                        out = model(dfg_data)
                    else:
                        ast_data = _build_pyg_from_ast_item(ast_item).to(str(device))
                        dfg_data = _build_pyg_from_dfg_item(dfg_item).to(str(device))
                        out = model(ast_data, dfg_data)
                    loss = criterion(out, y)
                    loss.backward()
                    optimizer.step()

                    total_loss += loss.item()
                    pred = out.argmax(dim=1)
                    total_correct += int((pred == y).sum().item())
                    total += 1

                    # collect eval buffers (probability of positive class)
                    prob_pos = torch.softmax(out.detach(), dim=1)[0, 1].item()
                    eval_probs.append(float(prob_pos))
                    eval_labels.append(int(y.item()))

                # Update batch progress with running metrics
                if total > 0:
                    current_loss = total_loss / total
                    current_acc = total_correct / total
                    progress.update(
                        batch_task,
                        advance=1,
                        loss=float(current_loss),
                        acc=float(current_acc),
                    )

            avg_loss = total_loss / max(total, 1)
            avg_acc = total_correct / max(total, 1)
            # compute evaluation metrics for the epoch
            metrics = compute_binary_classification_metrics(
                eval_labels, eval_probs, threshold=0.5
            )
            # persist metrics and plots
            try:
                save_epoch_metrics_and_plots(
                    results_dir,
                    ep,
                    eval_labels,
                    eval_probs,
                    metrics,
                )
            except Exception:
                pass

            # Saliency (optional, single sample from last batch each epoch)
            try:
                if cfg.explain:
                    example_dir = os.path.join(results_dir, f"epoch_{ep:02d}")
                    if last_batch is not None and last_B > 0:
                        i = 0
                        if cfg.mode == "ast":
                            ast_data = _build_pyg_from_ast_item(
                                last_batch["ast_graph"][i]
                            ).to(str(device))
                            dfg_data = None
                        elif cfg.mode == "dfg":
                            ast_data = None
                            dfg_data = _build_pyg_from_dfg_item(
                                last_batch["dfg_graph"][i]
                            ).to(str(device))
                        else:
                            ast_data = _build_pyg_from_ast_item(
                                last_batch["ast_graph"][i]
                            ).to(str(device))
                            dfg_data = _build_pyg_from_dfg_item(
                                last_batch["dfg_graph"][i]
                            ).to(str(device))
                        node_sal, param_sal = compute_node_saliency(
                            model, ast_data, dfg_data
                        )
                        if "ast" in node_sal:
                            save_saliency_heatmap(
                                example_dir, "ast_saliency", node_sal["ast"]
                            )
                        if "dfg" in node_sal:
                            save_saliency_heatmap(
                                example_dir, "dfg_saliency", node_sal["dfg"]
                            )
                        save_parameter_saliency_heatmaps(example_dir, param_sal)
            except Exception:
                pass
            if batch_total is not None:
                progress.update(batch_task, completed=batch_count)
            progress.remove_task(batch_task)
            progress.update(
                epoch_task, advance=1, loss=float(avg_loss), acc=float(avg_acc)
            )
            console.print(
                f"[cyan]Epoch {ep}[/cyan]  "
                f"loss: [bold]{avg_loss:.4f}[/bold]  "
                f"acc: [bold]{avg_acc:.3f}[/bold]  "
                f"f1: [bold]{(metrics['f1'] if metrics['f1'] is not None else float('nan')):.3f}[/bold]  "
                f"auroc: [bold]{(metrics['auroc'] if metrics['auroc'] is not None else float('nan')):.3f}[/bold]  "
                f"samples: [bold]{total}[/bold]  batches: [bold]{batch_count}[/bold]"
            )
            console.print("")

    # Save final weights
    weights_path = f"{results_dir}/latefusion_v1.pt"
    torch.save(model.state_dict(), weights_path)
    console.print(f"Saved model weights → {weights_path}", style="green")

    return results_dir


def parse_args() -> TrainConfig:

    p = argparse.ArgumentParser(
        description="Train LateFusion on HF streaming dataset (training-only)"
    )
    p.add_argument(
        "--repo_id",
        type=str,
        required=True,
        help='Hugging Face dataset repo, e.g. "org/name"',
    )
    p.add_argument("--split", type=str, default="train")
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight_decay", type=float, default=0.01)
    p.add_argument("--device", type=str, default="cuda:1")
    p.add_argument("--batch_size", type=int, default=32)
    p.add_argument("--num_workers", type=int, default=0)
    p.add_argument("--pin_memory", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--hid", type=int, default=64)
    p.add_argument("--gnn_layers", type=int, default=3)
    p.add_argument("--fusion_depth", type=int, default=2)
    p.add_argument("--shuffle_buffer", type=int, default=10_000)
    p.add_argument(
        "--save", type=str, default="", help="Optional run name under ./result/"
    )
    p.add_argument(
        "--mode",
        type=str,
        choices=["both", "ast", "dfg"],
        default="both",
        help="Which modalities to use (both | ast | dfg)",
    )
    p.add_argument(
        "--explain",
        action="store_true",
        help="If set, generate saliency after evaluation each epoch (last batch)",
    )
    p.add_argument(
        "--model",
        type=str,
        choices=["default", "gnn"],
        default="default",
        help="Model family: default late-fusion stack or the creative GNN variant.",
    )
    p.add_argument(
        "--loss",
        type=str,
        choices=["cross_entropy", "focal"],
        default="focal",
        help="Loss to optimise. Focal improves recall on imbalanced data.",
    )
    p.add_argument(
        "--focal_gamma",
        type=float,
        default=2.0,
        help="Gamma parameter for focal loss (ignored unless --loss=focal)",
    )
    a = p.parse_args()
    return TrainConfig(
        repo_id=a.repo_id,
        split=a.split,
        epochs=a.epochs,
        lr=a.lr,
        weight_decay=a.weight_decay,
        device=a.device,
        batch_size=a.batch_size,
        num_workers=a.num_workers,
        pin_memory=a.pin_memory,
        seed=a.seed,
        hid=a.hid,
        gnn_layers=a.gnn_layers,
        fusion_depth=a.fusion_depth,
        shuffle_buffer=a.shuffle_buffer,
        save_name=(a.save or None),
        mode=a.mode,
        explain=bool(a.explain),
        loss=a.loss,
        focal_gamma=a.focal_gamma,
        model=a.model,
    )


def main() -> None:
    cfg = parse_args()
    train(cfg)


if __name__ == "__main__":
    main()
