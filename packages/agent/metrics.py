#!/usr/bin/env python3
"""
Classification evaluation metrics utilities.

Pure numpy implementation to avoid extra dependencies. Safe for imbalanced
binary tasks; returns NA (None) for metrics that cannot be computed when a
class is missing.
"""

import math
import os
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np


def _safe_makedirs(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def compute_binary_classification_metrics(
    y_true: Iterable[int],
    y_prob_pos: Iterable[float],
    threshold: float = 0.5,
) -> Dict[str, Optional[float]]:
    """
    Compute accuracy, precision, recall, F1, AUROC for binary classification.

    - y_true: iterable of 0/1
    - y_prob_pos: iterable of P(y==1) in [0,1]
    - threshold: probability threshold to convert to hard labels
    """
    y_true_arr = np.asarray(list(y_true), dtype=np.int64)
    y_prob_arr = np.asarray(list(y_prob_pos), dtype=np.float32)
    if y_true_arr.size == 0:
        return {
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "auroc": None,
        }

    y_pred = (y_prob_arr >= threshold).astype(np.int64)

    tp = int(np.sum((y_pred == 1) & (y_true_arr == 1)))
    tn = int(np.sum((y_pred == 0) & (y_true_arr == 0)))
    fp = int(np.sum((y_pred == 1) & (y_true_arr == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true_arr == 1)))

    acc = (tp + tn) / max(len(y_true_arr), 1)
    prec = _safe_div(tp, tp + fp)
    rec = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * prec * rec, prec + rec) if (prec + rec) > 0 else 0.0

    # AUROC (binary, trapezoidal rule). If only one class present, return None.
    try:
        auroc = _compute_auc_binary(y_true_arr, y_prob_arr)
    except Exception:
        auroc = None

    return {
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "auroc": None if auroc is None else float(auroc),
    }


def _compute_auc_binary(y_true: np.ndarray, y_score: np.ndarray) -> Optional[float]:
    # If both classes not present, AUC undefined
    classes = np.unique(y_true)
    if classes.size < 2:
        return None

    # Sort by score descending
    order = np.argsort(-y_score)
    y_true = y_true[order]
    y_score = y_score[order]

    # Compute TPR/FPR ROC curve
    P = np.sum(y_true == 1)
    N = np.sum(y_true == 0)
    if P == 0 or N == 0:
        return None

    # Accumulate counts at distinct thresholds
    tps = 0
    fps = 0
    prev_score: Optional[float] = None
    roc_points: List[Tuple[float, float]] = [(0.0, 0.0)]

    for i in range(len(y_true)):
        score = float(y_score[i])
        label = int(y_true[i])
        if prev_score is not None and score != prev_score:
            # record point
            tpr = tps / P
            fpr = fps / N
            roc_points.append((fpr, tpr))
        if label == 1:
            tps += 1
        else:
            fps += 1
        prev_score = score

    # final point
    roc_points.append((fps / N, tps / P))
    # Ensure last point is (1,1)
    if roc_points[-1] != (1.0, 1.0):
        roc_points.append((1.0, 1.0))

    # Sort by FPR and integrate by trapezoids
    roc_points.sort(key=lambda p: p[0])
    auc = 0.0
    for i in range(1, len(roc_points)):
        x0, y0 = roc_points[i - 1]
        x1, y1 = roc_points[i]
        auc += (x1 - x0) * (y0 + y1) / 2.0
    return auc


def save_epoch_metrics_and_plots(
    out_dir: str,
    epoch: int,
    y_true: Iterable[int],
    y_prob_pos: Iterable[float],
    metrics: Dict[str, Optional[float]],
) -> None:
    """
    Save metrics.json and, if matplotlib is available, ROC/PR curves and a confusion matrix.
    Files are saved under {out_dir}/epoch_{epoch:02d}/.
    """
    y_true_arr = np.asarray(list(y_true), dtype=np.int64)
    y_prob_arr = np.asarray(list(y_prob_pos), dtype=np.float32)
    y_pred_arr = (y_prob_arr >= 0.5).astype(np.int64)

    ep_dir = os.path.join(out_dir, f"epoch_{epoch:02d}")
    _safe_makedirs(ep_dir)

    # Save raw arrays for reproducibility
    np.save(os.path.join(ep_dir, "y_true.npy"), y_true_arr)
    np.save(os.path.join(ep_dir, "y_prob.npy"), y_prob_arr)
    np.save(os.path.join(ep_dir, "y_pred.npy"), y_pred_arr)

    # Save metrics JSON
    import json as _json

    with open(os.path.join(ep_dir, "metrics.json"), "w", encoding="utf-8") as f:
        _json.dump(metrics, f, indent=2)

    # Optionally generate plots
    try:
        import matplotlib.pyplot as plt
        from sklearn.metrics import auc as _sk_auc
        from sklearn.metrics import confusion_matrix, precision_recall_curve, roc_curve

        # ROC
        if len(np.unique(y_true_arr)) > 1:
            fpr, tpr, _ = roc_curve(y_true_arr, y_prob_arr)
            roc_auc = _sk_auc(fpr, tpr)
            plt.figure()
            plt.plot(fpr, tpr, label=f"ROC AUC = {roc_auc:.3f}")
            plt.plot([0, 1], [0, 1], "k--")
            plt.xlabel("False Positive Rate")
            plt.ylabel("True Positive Rate")
            plt.legend(loc="lower right")
            plt.title("ROC Curve")
            plt.tight_layout()
            plt.savefig(os.path.join(ep_dir, "roc.png"))
            plt.close()

        # PR
        prec, rec, _ = precision_recall_curve(y_true_arr, y_prob_arr)
        plt.figure()
        plt.plot(rec, prec)
        plt.xlabel("Recall")
        plt.ylabel("Precision")
        plt.title("Precision-Recall Curve")
        plt.tight_layout()
        plt.savefig(os.path.join(ep_dir, "pr.png"))
        plt.close()

        # Confusion matrix
        cm = confusion_matrix(y_true_arr, y_pred_arr)
        plt.figure()
        im = plt.imshow(cm, cmap="Blues")
        plt.colorbar(im)
        plt.title("Confusion Matrix")
        plt.xlabel("Predicted")
        plt.ylabel("True")
        for (i, j), v in np.ndenumerate(cm):
            plt.text(j, i, f"{int(v)}", ha="center", va="center")
        plt.tight_layout()
        plt.savefig(os.path.join(ep_dir, "confusion_matrix.png"))
        plt.close()
    except Exception:
        # plotting optional; skip if libs not present
        pass
