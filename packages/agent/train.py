import argparse
import csv
import os
from datetime import datetime
from math import sqrt
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from dataset.analysis import DataAnalysis
from dataset.JsonDataset import PairedGraphDataset, paired_collate_fn
from model.LateFusion import LateFusionModel
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from torch.utils.data import DataLoader as TorchDataLoader
from torch_geometric.data import Data  # pyright: ignore[reportMissingImports]


# ----------------------------
# Train/eval loops
# ----------------------------
def _compute_confusion_metrics(tp: int, tn: int, fp: int, fn: int) -> Dict[str, float]:
    eps = 1e-12
    precision = tp / max(tp + fp, 1) if (tp + fp) > 0 else 0.0
    recall = tp / max(tp + fn, 1) if (tp + fn) > 0 else 0.0
    specificity = tn / max(tn + fp, 1) if (tn + fp) > 0 else 0.0
    accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)
    f1 = (
        (2 * precision * recall) / max(precision + recall, eps)
        if (precision + recall) > 0
        else 0.0
    )
    balanced_acc = (recall + specificity) / 2.0
    denom = sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn) - (fp * fn)) / denom if denom > 0 else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "accuracy": accuracy,
        "f1": f1,
        "balanced_acc": balanced_acc,
        "mcc": mcc,
    }


def _roc_auc_score(y_true: List[int], y_score: List[float]) -> float:
    if len(y_true) == 0:
        return 0.0
    # sort by score descending
    order = np.argsort(-np.asarray(y_score))
    y_true_sorted = np.asarray(y_true)[order]
    y_score_sorted = np.asarray(y_score)[order]
    P = np.sum(y_true_sorted)
    N = len(y_true_sorted) - P
    if P == 0 or N == 0:
        return 0.0
    # Compute ROC via thresholds at unique scores
    tprs = [0.0]
    fprs = [0.0]
    tp = 0
    fp = 0
    last_score = None
    for i in range(len(y_score_sorted)):
        score = y_score_sorted[i]
        label = y_true_sorted[i]
        if last_score is not None and score != last_score:
            tprs.append(tp / P)
            fprs.append(fp / N)
        if label == 1:
            tp += 1
        else:
            fp += 1
        last_score = score
    # final point
    tprs.append(tp / P)
    fprs.append(fp / N)
    # trapezoidal rule
    auc = 0.0
    for i in range(1, len(tprs)):
        auc += (fprs[i] - fprs[i - 1]) * (tprs[i] + tprs[i - 1]) / 2.0
    return float(auc)


def _global_param_l2_norm(model: nn.Module) -> float:
    s = 0.0
    with torch.no_grad():
        for p in model.parameters():
            if p is not None:
                s += float(torch.sum(p.detach() ** 2).item())
    return float(sqrt(max(s, 0.0)))


def _named_param_top_norms(model: nn.Module, k: int = 8) -> Dict[str, float]:
    norms: List[Tuple[str, float]] = []
    with torch.no_grad():
        for name, p in model.named_parameters():
            if p is None:
                continue
            val = float(torch.linalg.vector_norm(p.detach()).item())
            norms.append((name, val))
    norms.sort(key=lambda x: x[1], reverse=True)
    return {name: val for name, val in norms[:k]}


def _roc_curve_points(
    y_true: List[int], y_score: List[float]
) -> Tuple[List[float], List[float]]:
    if not y_true:
        return [0.0, 1.0], [0.0, 1.0]
    order = np.argsort(-np.asarray(y_score))
    y_true_sorted = np.asarray(y_true)[order]
    y_score_sorted = np.asarray(y_score)[order]
    P = np.sum(y_true_sorted)
    N = len(y_true_sorted) - P
    if P == 0 or N == 0:
        return [0.0, 1.0], [0.0, 1.0]
    tprs = [0.0]
    fprs = [0.0]
    tp = 0
    fp = 0
    last = None
    for i in range(len(y_score_sorted)):
        s = y_score_sorted[i]
        y = y_true_sorted[i]
        if last is not None and s != last:
            tprs.append(tp / P)
            fprs.append(fp / N)
        if y == 1:
            tp += 1
        else:
            fp += 1
        last = s
    tprs.append(tp / P)
    fprs.append(fp / N)
    return list(fprs), list(tprs)


def train_epoch(model, loader, optimizer, device, criterion: nn.Module):
    model.train()
    total_loss, total_correct, total = 0, 0, 0
    true_positives = true_negatives = false_positives = false_negatives = 0
    y_true: List[int] = []
    y_score: List[float] = []
    for batch in loader:
        # batch is dict from our collate: we parallel the first element of lists
        ast_item = batch["ast"][0]
        dfg_item = batch["dfg"][0]
        y = batch["label"][0].unsqueeze(0).to(device)

        ast_data = ast_item.to(device)
        dfg_data = dfg_item.to(device)

        optimizer.zero_grad()
        out = model(ast_data, dfg_data)
        loss = criterion(out, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        pred = out.argmax(dim=1)
        prob = torch.softmax(out, dim=1)[0, 1].item()
        total_correct += (pred == y).sum().item()
        # confusion counts (binary 0/1)
        py = int(pred.item())
        yy = int(y.item())
        y_true.append(yy)
        y_score.append(prob)
        if py == 1 and yy == 1:
            true_positives += 1
        elif py == 0 and yy == 0:
            true_negatives += 1
        elif py == 1 and yy == 0:
            false_positives += 1
        elif py == 0 and yy == 1:
            false_negatives += 1
        total += 1
    return (
        total_loss / total,
        total_correct / total,
        {
            "true_positives": true_positives,
            "true_negatives": true_negatives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        },
        y_true,
        y_score,
    )


def eval_epoch(model, loader, device, criterion: nn.Module):
    model.eval()
    total_loss, total_correct, total = 0, 0, 0
    true_positives = true_negatives = false_positives = false_negatives = 0
    y_true: List[int] = []
    y_score: List[float] = []
    with torch.no_grad():
        for batch in loader:
            ast_item = batch["ast"][0]
            dfg_item = batch["dfg"][0]
            y = batch["label"][0].unsqueeze(0).to(device)

            out = model(ast_item.to(device), dfg_item.to(device))
            loss = criterion(out, y)
            total_loss += loss.item()
            pred = out.argmax(dim=1)
            prob = torch.softmax(out, dim=1)[0, 1].item()
            total_correct += (pred == y).sum().item()
            py = int(pred.item())
            yy = int(y.item())
            y_true.append(yy)
            y_score.append(prob)
            if py == 1 and yy == 1:
                true_positives += 1
            elif py == 0 and yy == 0:
                true_negatives += 1
            elif py == 1 and yy == 0:
                false_positives += 1
            elif py == 0 and yy == 1:
                false_negatives += 1
            total += 1
    return (
        total_loss / total,
        total_correct / total,
        {
            "true_positives": true_positives,
            "true_negatives": true_negatives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        },
        y_true,
        y_score,
    )


def _compute_class_weights(
    train_indices: List[int], dataset: Any, device: torch.device
) -> torch.Tensor:
    positives = 0
    negatives = 0
    for idx in train_indices:
        item = dataset[idx]
        label = (
            int(item["label"])
            if isinstance(item.get("label"), (int, bool))
            else int(item["label"])
        )
        if label == 1:
            positives += 1
        else:
            negatives += 1
    # Avoid zero division; default to 1.0 if counts missing
    if positives == 0 or negatives == 0:
        return torch.tensor([1.0, 1.0], dtype=torch.float, device=device)
    pos_weight = negatives / max(positives, 1)
    neg_weight = 1.0
    return torch.tensor([neg_weight, pos_weight], dtype=torch.float, device=device)


def _format_metrics_row(
    epoch: int,
    split: str,
    loss: float,
    acc: float,
    metrics: Dict[str, float],
    auc: float,
    pred_pos_rate: float,
    best_thr: str = "-",
    best_f1: str = "-",
) -> List[str]:
    """Helper function to format a metrics row for the table display."""
    return [
        f"{epoch}",
        split,
        f"{loss:.4f}",
        f"{acc:.3f}",
        f"{metrics['precision']:.3f}",
        f"{metrics['recall']:.3f}",
        f"{metrics['f1']:.3f}",
        f"{metrics['specificity']:.3f}",
        f"{metrics['balanced_acc']:.3f}",
        f"{metrics['mcc']:.3f}",
        f"{auc:.3f}",
        f"{pred_pos_rate:.3f}",
        best_thr,
        best_f1,
    ]


def _format_csv_row(
    epoch: int,
    split: str,
    loss: float,
    acc: float,
    metrics: Dict[str, float],
    auc: float,
    confusion: Dict[str, int],
) -> List[Any]:
    """Helper function to format a metrics row for CSV writing."""
    return [
        epoch,
        split,
        round(loss, 6),
        round(acc, 6),
        round(metrics["precision"], 6),
        round(metrics["recall"], 6),
        round(metrics["f1"], 6),
        round(metrics["specificity"], 6),
        round(metrics["balanced_acc"], 6),
        round(metrics["mcc"], 6),
        round(auc, 6),
        confusion["true_positives"],
        confusion["true_negatives"],
        confusion["false_positives"],
        confusion["false_negatives"],
    ]


def _best_f1_threshold(y_true: List[int], y_score: List[float]) -> Tuple[float, float]:
    if not y_true:
        return 0.5, 0.0
    # Use unique score thresholds
    scores = sorted(set(y_score), reverse=True)
    best_f1 = -1.0
    best_thr = 0.5
    for thr in scores:
        tp = fp = fn = 0
        for yt, ys in zip(y_true, y_score):
            pred = 1 if ys >= thr else 0
            if pred == 1 and yt == 1:
                tp += 1
            elif pred == 1 and yt == 0:
                fp += 1
            elif pred == 0 and yt == 1:
                fn += 1
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        if f1 > best_f1:
            best_f1 = f1
            best_thr = thr
    return best_thr, best_f1


# ----------------------------
# main()
# ----------------------------
def _build_pyg_from_ast_item(ast_item: Dict[str, Any]) -> Data:
    # Create toy node features from AST nodes' feat dict; edge_attr from edges_ast_pc type
    nodes = ast_item.get("nodes", [])
    if not nodes:
        # fallback tiny graph
        x = torch.zeros((1, 2), dtype=torch.float)
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, 1), dtype=torch.float)
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

    # Build node features and sid->row map
    sid_to_row: Dict[int, int] = {}
    feats: List[List[float]] = []
    for i, n in enumerate(nodes):
        sid = int(n.get("sid", i))
        sid_to_row[sid] = i
        f = n.get("feat", {})
        feats.append([float(f.get("node_type_id", 0.0)), float(f.get("in_loop", 0.0))])
    x = torch.tensor(feats, dtype=torch.float)

    # edges as (src_sid, dst_sid, t)
    pc = ast_item.get("edges_ast_pc", [])
    ei_list: List[List[int]] = []
    ea_list: List[List[float]] = []
    for u, v, t in pc:
        if int(u) in sid_to_row and int(v) in sid_to_row:
            ei_list.append([sid_to_row[int(u)], sid_to_row[int(v)]])
            ea_list.append([float(t)])
    if ei_list:
        edge_index = torch.tensor(np.array(ei_list).T, dtype=torch.long)
        # ensure at least 1-dim edge_attr and float dtype
        edge_attr = torch.tensor(ea_list, dtype=torch.float)
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_attr = torch.empty((0, 1), dtype=torch.float)
    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)


def _build_pyg_from_dfg_item(dfg_item: Dict[str, Any]) -> Data:
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


def _normalize_graph_entry(entry: Any, kind: str) -> Dict[str, Any]:
    """Return a single graph object (first function) from a dataset entry that may be list/dict."""
    # AST: usually List[ASTGraph]; DFG: List[DFGGraph]
    if isinstance(entry, list):
        if not entry:
            raise ValueError(f"Empty {kind} graph list")
        return entry[0]
    if isinstance(entry, dict):
        # If wrapped AST-like
        if (
            kind == "ast"
            and "ast_result" in entry
            and isinstance(entry["ast_result"], dict)
        ):
            return entry["ast_result"]
        # If already a single graph object
        if "nodes" in entry:
            return entry
    raise ValueError(f"Unsupported {kind} graph entry type: {type(entry)}")


def _pair_iter(
    ast_batch: Dict[str, Any], dfg_batch: Dict[str, Any]
) -> List[Tuple[Data, Data, torch.Tensor]]:
    pairs: List[Tuple[Data, Data, torch.Tensor]] = []
    n = min(len(ast_batch["graph"]), len(dfg_batch["graph"]))
    for i in range(n):
        ast_entry = ast_batch["graph"][i]
        dfg_entry = dfg_batch["graph"][i]
        y = ast_batch["label"][i]

        ast_item = _normalize_graph_entry(ast_entry, kind="ast")
        dfg_item = _normalize_graph_entry(dfg_entry, kind="dfg")

        ast_data = _build_pyg_from_ast_item(ast_item)
        dfg_data = _build_pyg_from_dfg_item(dfg_item)
        pairs.append((ast_data, dfg_data, y))
    return pairs


def get_arg_parser() -> argparse.ArgumentParser:
    """Deprecated CLI parser retained for compatibility; not used by main().

    Use run_sweep.py or pass an argparse.Namespace to train_with_args().
    """
    p = argparse.ArgumentParser(description="Train Late-Fusion on AST/DFG graphs")
    # Kept for backward compatibility; defaults mirror internal defaults
    p.add_argument("--ast_dir", type=str, required=True)
    p.add_argument("--dfg_dir", type=str, required=True)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight_decay", type=float, default=0.01)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--split", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=42)
    # Additional hyperparameters for sweeps
    p.add_argument("--hid", type=int, default=64)
    p.add_argument("--gnn_layers", type=int, default=3)
    p.add_argument("--fusion_depth", type=int, default=2)
    p.add_argument("--batch_size", type=int, default=32)
    p.add_argument("--num_workers", type=int, default=0)
    p.add_argument("--pin_memory", action="store_true")
    # Saving control: if provided, use as results subdirectory name under result/
    p.add_argument(
        "--save",
        type=str,
        default="",
        help="Optional results name; default timestamp if empty",
    )
    return p


def train_with_args(args: argparse.Namespace) -> str:
    # Resolve defaults for missing attributes to make hyperparameters widely available
    ast_dir = getattr(args, "ast_dir")
    dfg_dir = getattr(args, "dfg_dir")
    epochs = int(getattr(args, "epochs", 5))
    lr = float(getattr(args, "lr", 1e-3))
    weight_decay = float(getattr(args, "weight_decay", 0.01))
    device_str = str(getattr(args, "device", "cpu"))
    split = float(getattr(args, "split", 0.8))
    seed = int(getattr(args, "seed", 42))
    hid = int(getattr(args, "hid", 64))
    gnn_layers = int(getattr(args, "gnn_layers", 3))
    fusion_depth = int(getattr(args, "fusion_depth", 2))
    batch_size = int(getattr(args, "batch_size", 32))
    num_workers = int(getattr(args, "num_workers", 0))
    pin_memory = bool(getattr(args, "pin_memory", False))
    save_name_in = str(getattr(args, "save", "")).strip()

    paired_ds = PairedGraphDataset(ast_dir, dfg_dir)

    # Validate dataset has samples and adjust split to keep train non-empty
    n = len(paired_ds)
    if n == 0:
        raise ValueError(
            f"PairedGraphDataset is empty. Check ast_dir='{ast_dir}' and dfg_dir='{dfg_dir}' contain matching files."
        )

    # Results directory with timestamp or provided --save name
    timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
    save_name = save_name_in
    if not save_name:
        save_name = timestamp
    results_dir = os.path.join(os.getcwd(), "result", save_name)
    os.makedirs(results_dir, exist_ok=True)

    # Random split (80/20 default)
    idx = np.arange(n)
    rng = np.random.default_rng(seed)
    rng.shuffle(idx)
    split_at = int(n * float(split))
    if split_at <= 0:
        split_at = 1
    if split_at >= n:
        split_at = n - 1 if n > 1 else 1
    train_idx = idx[:split_at].tolist()
    eval_idx = idx[split_at:].tolist()

    from torch.utils.data import Subset

    train_ds = Subset(paired_ds, train_idx)
    eval_ds = Subset(paired_ds, eval_idx)

    # ----------------------------
    # Data analysis (label distribution)
    # ----------------------------
    def _count_labels(indices):
        pos = 0
        neg = 0
        for i in indices:
            item = paired_ds[i]
            y = (
                int(item["label"])
                if isinstance(item.get("label"), (int, bool))
                else int(item["label"])
            )
            if y == 1:
                pos += 1
            else:
                neg += 1
        return pos, neg

    all_pos, all_neg = _count_labels(list(range(len(paired_ds))))
    tr_pos, tr_neg = _count_labels(train_idx)
    ev_pos, ev_neg = _count_labels(eval_idx)

    def _bar(pos, neg, width=30):
        total = max(pos + neg, 1)
        pos_w = int(width * (pos / total))
        neg_w = width - pos_w
        return f"[green]{'█'*pos_w}[/green][red]{'█'*neg_w}[/red]"

    console = Console()
    console.rule("Dataset Label Distribution")
    dist_table = Table(show_header=True, header_style="bold cyan")
    dist_table.add_column("Split")
    dist_table.add_column("Total", justify="right")
    dist_table.add_column("Positives", justify="right")
    dist_table.add_column("Negatives", justify="right")
    dist_table.add_column("Positive %", justify="right")
    dist_table.add_column("Imbalance (Neg:Pos)", justify="right")
    dist_table.add_column("Bar")

    def _add_row(name, pos, neg):
        total = pos + neg
        pos_pct = (pos / total * 100.0) if total > 0 else 0.0
        imb = (neg / max(pos, 1)) if pos > 0 else float("inf")
        dist_table.add_row(
            name,
            f"{total}",
            f"{pos}",
            f"{neg}",
            f"{pos_pct:.2f}%",
            f"{imb:.2f}x",
            _bar(pos, neg),
        )

    _add_row("Overall", all_pos, all_neg)
    _add_row("Train", tr_pos, tr_neg)
    _add_row("Eval", ev_pos, ev_neg)
    console.print(dist_table)

    analysis = DataAnalysis(results_dir)
    analysis.save_dataset_profile(
        paired_ds,
        label_counts={
            "overall": {"pos": all_pos, "neg": all_neg},
            "train": {"pos": tr_pos, "neg": tr_neg},
            "eval": {"pos": ev_pos, "neg": ev_neg},
        },
    )

    # Suggested class weights (neg, pos)
    if tr_pos > 0 and tr_neg > 0:
        suggested_pos_w = tr_neg / tr_pos
        console.print(
            f"Suggested class weights -> negative: 1.0, positive: {suggested_pos_w:.2f}",
            style="italic dim",
        )

    train_loader = TorchDataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=paired_collate_fn,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )

    device = torch.device(device_str)

    # Peek one batch to infer dims
    first_batch = next(iter(train_loader))
    ast_graph_0 = first_batch["ast_graph"][0]
    dfg_graph_0 = first_batch["dfg_graph"][0]
    ast_data = _build_pyg_from_ast_item(ast_graph_0[0])
    dfg_data = _build_pyg_from_dfg_item(dfg_graph_0[0])
    ast_in = int(getattr(ast_data, "x").size(1))
    ast_edge_attr = getattr(ast_data, "edge_attr", torch.empty(0))
    ast_edge = int(ast_edge_attr.size(1)) if ast_edge_attr.numel() > 0 else 0
    dfg_in = int(getattr(dfg_data, "x").size(1))
    dfg_edge_attr = getattr(dfg_data, "edge_attr", torch.empty(0))
    dfg_edge = int(dfg_edge_attr.size(1)) if dfg_edge_attr.numel() > 0 else 0

    # Ensure edge dims are at least 1 so GINEConv has a defined edge_dim
    ast_edge = max(1, ast_edge)
    dfg_edge = max(1, dfg_edge)
    model = LateFusionModel(
        ast_in,
        ast_edge,
        dfg_in,
        dfg_edge,
        hid=hid,
        out_classes=2,
        gnn_layers=gnn_layers,
        fusion_depth=fusion_depth,
    ).to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    # Class-weighted loss to address imbalance
    class_weights = _compute_class_weights(train_idx, paired_ds, device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    # Per-epoch metrics will be recorded via analysis

    # Initialize final evaluation data for ROC curve
    final_ev_y_true: List[int] = []
    final_ev_y_score: List[float] = []

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("• Elapsed:"),
        TimeElapsedColumn(),
        TextColumn("• ETA:"),
        TimeRemainingColumn(),
    ) as progress:
        epoch_task = progress.add_task("Training", total=epochs)
        for ep in range(1, epochs + 1):
            steps = len(train_loader)
            step_task = progress.add_task(f"Epoch {ep}", total=steps)
            total_loss = total_correct = total = 0
            tr_confusion = {
                "true_positives": 0,
                "true_negatives": 0,
                "false_positives": 0,
                "false_negatives": 0,
            }
            tr_y_true: List[int] = []
            tr_y_score: List[float] = []
            for batch in train_loader:
                # batch size 1 is assumed, but keep generic iteration
                for i in range(len(batch["label"])):
                    y = batch["label"][i].unsqueeze(0)
                    ast_item = batch["ast_graph"][i][0]
                    dfg_item = batch["dfg_graph"][i][0]
                    tr_loss, tr_acc, cm, y_true_ep, y_score_ep = train_epoch(
                        model,
                        [
                            {
                                "ast": [_build_pyg_from_ast_item(ast_item)],
                                "dfg": [_build_pyg_from_dfg_item(dfg_item)],
                                "label": y,
                            }
                        ],
                        optim,
                        device,
                        criterion,
                    )
                    total_loss += tr_loss
                    total_correct += tr_acc
                    for key in tr_confusion:
                        tr_confusion[key] += cm[key]
                    tr_y_true.extend(y_true_ep)
                    tr_y_score.extend(y_score_ep)
                    total += 1
                progress.update(step_task, advance=1)
            avg_loss = total_loss / max(total, 1)
            avg_acc = total_correct / max(total, 1)
            progress.advance(epoch_task, 1)
            # Compute extended metrics for train
            tr_metrics = _compute_confusion_metrics(
                tr_confusion["true_positives"],
                tr_confusion["true_negatives"],
                tr_confusion["false_positives"],
                tr_confusion["false_negatives"],
            )
            tr_auc = _roc_auc_score(tr_y_true, tr_y_score)

            # Per-epoch evaluation on held-out split
            eval_loader = TorchDataLoader(
                eval_ds, batch_size=1, shuffle=False, collate_fn=paired_collate_fn
            )
            ev_total_loss = ev_total_acc = 0.0
            ev_total = 0
            ev_confusion = {
                "true_positives": 0,
                "true_negatives": 0,
                "false_positives": 0,
                "false_negatives": 0,
            }
            ev_y_true: List[int] = []
            ev_y_score: List[float] = []
            for batch in eval_loader:
                for i in range(len(batch["label"])):
                    y = batch["label"][i].unsqueeze(0)
                    ast_item = batch["ast_graph"][i][0]
                    dfg_item = batch["dfg_graph"][i][0]
                    ev_loss, ev_acc, cm, y_true_ep, y_score_ep = eval_epoch(
                        model,
                        [
                            {
                                "ast": [_build_pyg_from_ast_item(ast_item)],
                                "dfg": [_build_pyg_from_dfg_item(dfg_item)],
                                "label": y,
                            }
                        ],
                        device,
                        criterion,
                    )
                    ev_total_loss += ev_loss
                    ev_total_acc += ev_acc
                    for key in ev_confusion:
                        ev_confusion[key] += cm[key]
                    ev_y_true.extend(y_true_ep)
                    ev_y_score.extend(y_score_ep)
                    ev_total += 1

            ev_avg_loss = ev_total_loss / max(ev_total, 1)
            ev_avg_acc = ev_total_acc / max(ev_total, 1)
            ev_metrics = _compute_confusion_metrics(
                ev_confusion["true_positives"],
                ev_confusion["true_negatives"],
                ev_confusion["false_positives"],
                ev_confusion["false_negatives"],
            )
            ev_auc = _roc_auc_score(ev_y_true, ev_y_score)
            # Predicted positive rates
            tr_total = sum(tr_confusion.values())
            tr_pred_pos_rate = (
                tr_confusion["true_positives"] + tr_confusion["false_positives"]
            ) / max(tr_total, 1)

            ev_total = sum(ev_confusion.values())
            ev_pred_pos_rate = (
                ev_confusion["true_positives"] + ev_confusion["false_positives"]
            ) / max(ev_total, 1)
            # Best F1 threshold (eval)
            best_thr, best_f1 = _best_f1_threshold(ev_y_true, ev_y_score)

            # Render a Rich table for visibility
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Epoch", justify="right")
            table.add_column("Split")
            table.add_column("Loss")
            table.add_column("Accuracy")
            table.add_column("Precision")
            table.add_column("Recall")
            table.add_column("F1 Score")
            table.add_column("Specificity")
            table.add_column("Balanced Accuracy")
            table.add_column("Matthews Correlation Coefficient")
            table.add_column("Area Under ROC Curve")
            table.add_column("Predicted Positive Rate")
            table.add_column("Optimal Threshold (Eval)")
            table.add_column("F1 Score (Optimal)")
            table.add_row(
                *_format_metrics_row(
                    ep, "Train", avg_loss, avg_acc, tr_metrics, tr_auc, tr_pred_pos_rate
                )
            )
            table.add_row(
                *_format_metrics_row(
                    ep,
                    "Eval",
                    ev_avg_loss,
                    ev_avg_acc,
                    ev_metrics,
                    ev_auc,
                    ev_pred_pos_rate,
                    f"{best_thr:.3f}",
                    f"{best_f1:.3f}",
                )
            )
            progress.print(table)

            analysis.record_epoch(
                epoch=ep,
                train_loss=avg_loss,
                train_acc=avg_acc,
                train_metrics=tr_metrics,
                train_auc=tr_auc,
                train_pred_pos_rate=tr_pred_pos_rate,
                eval_loss=ev_avg_loss,
                eval_acc=ev_avg_acc,
                eval_metrics=ev_metrics,
                eval_auc=ev_auc,
                eval_pred_pos_rate=ev_pred_pos_rate,
                model=model,
            )

            # Store final epoch data for ROC curve
            if ep == epochs:
                final_ev_y_true = ev_y_true
                final_ev_y_score = ev_y_score

            # CSV logging for analysis
            csv_path = os.path.join(results_dir, "metrics.csv")
            write_header = not os.path.exists(csv_path)
            with open(csv_path, mode="a", newline="") as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow(
                        [
                            "epoch",
                            "split",
                            "loss",
                            "accuracy",
                            "precision",
                            "recall",
                            "f1_score",
                            "specificity",
                            "balanced_accuracy",
                            "matthews_correlation_coefficient",
                            "area_under_roc_curve",
                            "true_positives",
                            "true_negatives",
                            "false_positives",
                            "false_negatives",
                        ]
                    )
                writer.writerow(
                    _format_csv_row(
                        ep, "train", avg_loss, avg_acc, tr_metrics, tr_auc, tr_confusion
                    )
                )
                writer.writerow(
                    _format_csv_row(
                        ep,
                        "eval",
                        ev_avg_loss,
                        ev_avg_acc,
                        ev_metrics,
                        ev_auc,
                        ev_confusion,
                    )
                )

    # Save curves and ROC via centralized analysis helper
    analysis.save_curves()
    analysis.save_roc_curve(final_ev_y_true, final_ev_y_score)

    # Final evaluation summary moved into per-epoch logging above

    weights_path = os.path.join(results_dir, "latefusion_v1.pt")
    torch.save(model.state_dict(), weights_path)
    Console().print(
        f"Saved metrics to {os.path.join(results_dir, 'metrics.csv')} and model weights to {weights_path}",
        style="green",
    )

    return results_dir


def main():
    args = get_arg_parser().parse_args()
    train_with_args(args)


if __name__ == "__main__":
    main()
