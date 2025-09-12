import argparse
import csv
import os
from math import sqrt
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from dataset.JsonDataset import (
    GraphDataset,
    PairedGraphDataset,
    default_collate_fn,
    paired_collate_fn,
)
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


def train_epoch(model, loader, optimizer, device):
    model.train()
    total_loss, total_correct, total = 0, 0, 0
    criterion = nn.CrossEntropyLoss()
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


def eval_epoch(model, loader, device):
    model.eval()
    total_loss, total_correct, total = 0, 0, 0
    criterion = nn.CrossEntropyLoss()
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


def main():
    p = argparse.ArgumentParser(description="Train Late-Fusion on AST/DFG graphs")
    p.add_argument("--ast_dir", type=str, required=True)
    p.add_argument("--dfg_dir", type=str, required=True)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--split", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    paired_ds = PairedGraphDataset(args.ast_dir, args.dfg_dir)

    # Random split (80/20 default)
    n = len(paired_ds)
    idx = np.arange(n)
    rng = np.random.default_rng(args.seed)
    rng.shuffle(idx)
    split_at = int(n * float(args.split))
    train_idx = idx[:split_at].tolist()
    eval_idx = idx[split_at:].tolist()

    from torch.utils.data import Subset

    train_ds = Subset(paired_ds, train_idx)
    eval_ds = Subset(paired_ds, eval_idx)

    train_loader = TorchDataLoader(
        train_ds, batch_size=32, shuffle=True, collate_fn=paired_collate_fn
    )

    device = torch.device(args.device)

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
        ast_in, ast_edge, dfg_in, dfg_edge, hid=64, out_classes=2
    ).to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("• Elapsed:"),
        TimeElapsedColumn(),
        TextColumn("• ETA:"),
        TimeRemainingColumn(),
    ) as progress:
        epoch_task = progress.add_task("Training", total=args.epochs)
        for ep in range(1, args.epochs + 1):
            steps = len(train_loader)
            step_task = progress.add_task(f"Epoch {ep}", total=steps)
            total_loss = total_correct = total = 0
            tr_true_positives = tr_true_negatives = tr_false_positives = (
                tr_false_negatives
            ) = 0
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
                    )
                    total_loss += tr_loss
                    total_correct += tr_acc
                    tr_true_positives += cm["true_positives"]
                    tr_true_negatives += cm["true_negatives"]
                    tr_false_positives += cm["false_positives"]
                    tr_false_negatives += cm["false_negatives"]
                    tr_y_true.extend(y_true_ep)
                    tr_y_score.extend(y_score_ep)
                    total += 1
                progress.update(step_task, advance=1)
            avg_loss = total_loss / max(total, 1)
            avg_acc = total_correct / max(total, 1)
            progress.advance(epoch_task, 1)
            # Compute extended metrics for train
            tr_metrics = _compute_confusion_metrics(
                tr_true_positives,
                tr_true_negatives,
                tr_false_positives,
                tr_false_negatives,
            )
            tr_auc = _roc_auc_score(tr_y_true, tr_y_score)

            # Per-epoch evaluation on held-out split
            eval_loader = TorchDataLoader(
                eval_ds, batch_size=1, shuffle=False, collate_fn=paired_collate_fn
            )
            ev_total_loss = ev_total_acc = 0.0
            ev_total = 0
            ev_true_positives = ev_true_negatives = ev_false_positives = (
                ev_false_negatives
            ) = 0
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
                    )
                    ev_total_loss += ev_loss
                    ev_total_acc += ev_acc
                    ev_true_positives += cm["true_positives"]
                    ev_true_negatives += cm["true_negatives"]
                    ev_false_positives += cm["false_positives"]
                    ev_false_negatives += cm["false_negatives"]
                    ev_y_true.extend(y_true_ep)
                    ev_y_score.extend(y_score_ep)
                    ev_total += 1

            ev_avg_loss = ev_total_loss / max(ev_total, 1)
            ev_avg_acc = ev_total_acc / max(ev_total, 1)
            ev_metrics = _compute_confusion_metrics(
                ev_true_positives,
                ev_true_negatives,
                ev_false_positives,
                ev_false_negatives,
            )
            ev_auc = _roc_auc_score(ev_y_true, ev_y_score)

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
            table.add_row(
                f"{ep}",
                "Train",
                f"{avg_loss:.4f}",
                f"{avg_acc:.3f}",
                f"{tr_metrics['precision']:.3f}",
                f"{tr_metrics['recall']:.3f}",
                f"{tr_metrics['f1']:.3f}",
                f"{tr_metrics['specificity']:.3f}",
                f"{tr_metrics['balanced_acc']:.3f}",
                f"{tr_metrics['mcc']:.3f}",
                f"{tr_auc:.3f}",
            )
            table.add_row(
                f"{ep}",
                "Eval",
                f"{ev_avg_loss:.4f}",
                f"{ev_avg_acc:.3f}",
                f"{ev_metrics['precision']:.3f}",
                f"{ev_metrics['recall']:.3f}",
                f"{ev_metrics['f1']:.3f}",
                f"{ev_metrics['specificity']:.3f}",
                f"{ev_metrics['balanced_acc']:.3f}",
                f"{ev_metrics['mcc']:.3f}",
                f"{ev_auc:.3f}",
            )
            progress.print(table)

            # CSV logging for analysis
            csv_path = os.path.join(os.getcwd(), "metrics.csv")
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
                    [
                        ep,
                        "train",
                        round(avg_loss, 6),
                        round(avg_acc, 6),
                        round(tr_metrics["precision"], 6),
                        round(tr_metrics["recall"], 6),
                        round(tr_metrics["f1"], 6),
                        round(tr_metrics["specificity"], 6),
                        round(tr_metrics["balanced_acc"], 6),
                        round(tr_metrics["mcc"], 6),
                        round(tr_auc, 6),
                        tr_true_positives,
                        tr_true_negatives,
                        tr_false_positives,
                        tr_false_negatives,
                    ]
                )
                writer.writerow(
                    [
                        ep,
                        "eval",
                        round(ev_avg_loss, 6),
                        round(ev_avg_acc, 6),
                        round(ev_metrics["precision"], 6),
                        round(ev_metrics["recall"], 6),
                        round(ev_metrics["f1"], 6),
                        round(ev_metrics["specificity"], 6),
                        round(ev_metrics["balanced_acc"], 6),
                        round(ev_metrics["mcc"], 6),
                        round(ev_auc, 6),
                        ev_true_positives,
                        ev_true_negatives,
                        ev_false_positives,
                        ev_false_negatives,
                    ]
                )

    # Final evaluation summary moved into per-epoch logging above

    torch.save(model.state_dict(), "latefusion_v1.pt")


if __name__ == "__main__":
    main()


def train():
    pass


if __name__ == "__main__":
    train()
