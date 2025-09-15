import os
from math import sqrt
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn


class DataAnalysis:
    def __init__(self, results_dir: str) -> None:
        self.results_dir = results_dir
        os.makedirs(self.results_dir, exist_ok=True)
        # per-epoch series
        self.ep_train_loss: List[float] = []
        self.ep_eval_loss: List[float] = []
        self.ep_train_acc: List[float] = []
        self.ep_eval_acc: List[float] = []
        self.ep_train_f1: List[float] = []
        self.ep_eval_f1: List[float] = []
        self.ep_train_auc: List[float] = []
        self.ep_eval_auc: List[float] = []
        self.ep_tr_ppr: List[float] = []
        self.ep_ev_ppr: List[float] = []
        self.ep_param_norm: List[float] = []

    # ------------------- Dataset profiling -------------------
    def save_dataset_profile(
        self,
        paired_ds: Any,
        label_counts: Dict[str, Dict[str, int]],
    ) -> None:
        try:
            import json

            ast_nodes: List[int] = []
            ast_edges: List[int] = []
            dfg_nodes: List[int] = []
            dfg_edges: List[int] = []
            for i in range(len(paired_ds)):
                item = paired_ds[i]
                ag = item["ast_graph"][0]
                dg = item["dfg_graph"][0]
                ast_nodes.append(len(ag.get("nodes", [])))
                ast_edges.append(len(ag.get("edges_ast_pc", [])))
                dfg_nodes.append(len(dg.get("nodes", [])))
                dfg_edges.append(len(dg.get("edges", [])))

            def _stat(v: List[int]) -> Dict[str, float]:
                arr = np.asarray(v, dtype=float)
                if arr.size == 0:
                    return {"count": 0}
                return {
                    "count": int(arr.size),
                    "mean": float(arr.mean()),
                    "std": float(arr.std()),
                    "min": float(arr.min()),
                    "p50": float(np.percentile(arr, 50)),
                    "p90": float(np.percentile(arr, 90)),
                    "p99": float(np.percentile(arr, 99)),
                    "max": float(arr.max()),
                }

            profile = {
                "label_counts": label_counts,
                "ast_nodes": _stat(ast_nodes),
                "ast_edges_pc": _stat(ast_edges),
                "dfg_nodes": _stat(dfg_nodes),
                "dfg_edges": _stat(dfg_edges),
            }

            with open(
                os.path.join(self.results_dir, "data_profile.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(profile, f, indent=2)

            # Histograms
            self._save_hist_svg(ast_nodes, "ast_nodes_hist.svg", "AST Node Count Histogram")
            self._save_hist_svg(ast_edges, "ast_edges_hist.svg", "AST PC Edge Count Histogram")
            self._save_hist_svg(dfg_nodes, "dfg_nodes_hist.svg", "DFG Node Count Histogram")
            self._save_hist_svg(dfg_edges, "dfg_edges_hist.svg", "DFG Edge Count Histogram")
        except Exception:
            # Best-effort; avoid training disruption on profiling errors
            pass

    # ------------------- Epoch logging -------------------
    def record_epoch(
        self,
        *,
        epoch: int,
        train_loss: float,
        train_acc: float,
        train_metrics: Dict[str, float],
        train_auc: float,
        train_pred_pos_rate: float,
        eval_loss: float,
        eval_acc: float,
        eval_metrics: Dict[str, float],
        eval_auc: float,
        eval_pred_pos_rate: float,
        model: nn.Module,
    ) -> None:
        self.ep_train_loss.append(float(train_loss))
        self.ep_eval_loss.append(float(eval_loss))
        self.ep_train_acc.append(float(train_acc))
        self.ep_eval_acc.append(float(eval_acc))
        self.ep_train_f1.append(float(train_metrics.get("f1", 0.0)))
        self.ep_eval_f1.append(float(eval_metrics.get("f1", 0.0)))
        self.ep_train_auc.append(float(train_auc))
        self.ep_eval_auc.append(float(eval_auc))
        self.ep_tr_ppr.append(float(train_pred_pos_rate))
        self.ep_ev_ppr.append(float(eval_pred_pos_rate))
        gnorm = self._global_param_l2_norm(model)
        self.ep_param_norm.append(float(gnorm))
        # Append top param norms JSONL
        try:
            import json as _json

            top = self._named_param_top_norms(model, k=8)
            with open(
                os.path.join(self.results_dir, "param_norms_epoch.jsonl"),
                "a",
                encoding="utf-8",
            ) as jf:
                jf.write(
                    _json.dumps(
                        {
                            "epoch": int(epoch),
                            "global_param_l2": float(gnorm),
                            "top_param_norms": {k: float(v) for k, v in top.items()},
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass

    def save_curves(self) -> None:
        # Loss
        self._save_line(
            [("train", self.ep_train_loss), ("eval", self.ep_eval_loss)],
            "loss_curve.svg",
            "Loss over Epochs",
            "Loss",
        )
        # Accuracy
        self._save_line(
            [("train", self.ep_train_acc), ("eval", self.ep_eval_acc)],
            "acc_curve.svg",
            "Accuracy over Epochs",
            "Accuracy",
        )
        # F1
        self._save_line(
            [("train", self.ep_train_f1), ("eval", self.ep_eval_f1)],
            "f1_curve.svg",
            "F1 over Epochs",
            "F1",
        )
        # AUC
        self._save_line(
            [("train", self.ep_train_auc), ("eval", self.ep_eval_auc)],
            "auc_curve.svg",
            "AUC over Epochs",
            "AUC",
        )
        # Predicted positive rate
        self._save_line(
            [("train_pred_pos", self.ep_tr_ppr), ("eval_pred_pos", self.ep_ev_ppr)],
            "pred_pos_rate.svg",
            "Predicted Positive Rate",
            "Rate",
        )
        # Parameter norms
        self._save_line(
            [("param_l2_norm", self.ep_param_norm)],
            "param_norm.svg",
            "Parameter L2 Norm",
            "Norm",
        )

    def save_roc_curve(self, y_true: List[int], y_score: List[float]) -> None:
        fprs, tprs = self._roc_curve_points(y_true, y_score)
        width, height, margin = 500, 500, 50
        plot_w, plot_h = width - 2 * margin, height - 2 * margin
        parts = [
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>",
            f"<rect x='0' y='0' width='{width}' height='{height}' fill='white' />",
            f"<text x='{width/2}' y='20' text-anchor='middle' font-size='16'>ROC Curve (Eval)</text>",
            f"<line x1='{margin}' y1='{height-margin}' x2='{width-margin}' y2='{height-margin}' stroke='black' />",
            f"<line x1='{margin}' y1='{margin}' x2='{margin}' y2='{height-margin}' stroke='black' />",
        ]
        pts = []
        for fpr, tpr in zip(fprs, tprs):
            x = margin + float(fpr) * plot_w
            y = height - margin - float(tpr) * plot_h
            pts.append(f"{x:.2f},{y:.2f}")
        if pts:
            parts.append(
                f"<polyline fill='none' stroke='#d62728' stroke-width='2' points='{" ".join(pts)}' />"
            )
        parts.append("</svg>")
        with open(
            os.path.join(self.results_dir, "roc_curve.svg"), "w", encoding="utf-8"
        ) as f:
            f.write("\n".join(parts))

    # ------------------- Internal helpers -------------------
    @staticmethod
    def _global_param_l2_norm(model: nn.Module) -> float:
        s = 0.0
        with torch.no_grad():
            for p in model.parameters():
                if p is not None:
                    s += float(torch.sum(p.detach() ** 2).item())
        return float(sqrt(max(s, 0.0)))

    @staticmethod
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

    @staticmethod
    def _roc_curve_points(y_true: List[int], y_score: List[float]) -> Tuple[List[float], List[float]]:
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

    def _save_hist_svg(self, values: List[int], out_name: str, title: str, bins: int = 30) -> None:
        if not values:
            return
        vmin = float(min(values))
        vmax = float(max(values))
        if vmin == vmax:
            vmax = vmin + 1.0
        counts = [0 for _ in range(bins)]
        for v in values:
            b = int((float(v) - vmin) / (vmax - vmin) * bins)
            b = min(max(b, 0), bins - 1)
            counts[b] += 1
        width, height, margin = 800, 400, 50
        plot_w, plot_h = width - 2 * margin, height - 2 * margin
        max_c = max(counts) if counts else 1
        bar_w = plot_w / bins
        parts = [
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>",
            f"<rect x='0' y='0' width='{width}' height='{height}' fill='white' />",
            f"<text x='{width/2}' y='20' text-anchor='middle' font-size='16'>{title}</text>",
            f"<line x1='{margin}' y1='{margin}' x2='{margin}' y2='{height-margin}' stroke='black' />",
            f"<line x1='{margin}' y1='{height-margin}' x2='{width-margin}' y2='{height-margin}' stroke='black' />",
        ]
        for i, c in enumerate(counts):
            h = (c / max_c) * plot_h if max_c > 0 else 0
            x = margin + i * bar_w
            y = height - margin - h
            parts.append(
                f"<rect x='{x:.2f}' y='{y:.2f}' width='{bar_w-1:.2f}' height='{h:.2f}' fill='#1f77b4' />"
            )
        parts.append("</svg>")
        with open(os.path.join(self.results_dir, out_name), "w", encoding="utf-8") as fsvg:
            fsvg.write("\n".join(parts))

    def _save_line(
        self,
        series: List[Tuple[str, List[float]]],
        name: str,
        title: str,
        y_label: str,
    ) -> None:
        width, height, margin = 800, 400, 50
        xs = list(range(1, len(series[0][1]) + 1)) if series and series[0][1] else [1]
        y_vals = [v for _l, ys in series for v in ys]
        y_min = min(y_vals) if y_vals else 0.0
        y_max = max(y_vals) if y_vals else 1.0
        if y_min == y_max:
            y_min -= 0.5
            y_max += 0.5
        plot_w, plot_h = width - 2 * margin, height - 2 * margin

        def xy(i, y):
            x = margin + (i - 1) / max(len(xs) - 1, 1) * plot_w
            yn = (y - y_min) / (y_max - y_min)
            yy = margin + (1.0 - yn) * plot_h
            return x, yy

        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
        parts = [
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>",
            f"<rect x='0' y='0' width='{width}' height='{height}' fill='white' />",
            f"<text x='{width/2}' y='20' text-anchor='middle' font-size='16'>{title}</text>",
            f"<text x='15' y='{height/2}' transform='rotate(-90 15,{height/2})' text-anchor='middle' font-size='12'>{y_label}</text>",
            f"<line x1='{margin}' y1='{margin}' x2='{margin}' y2='{height-margin}' stroke='black' />",
            f"<line x1='{margin}' y1='{height-margin}' x2='{width-margin}' y2='{height-margin}' stroke='black' />",
        ]
        for idx, (label, ys) in enumerate(series):
            color = colors[idx % len(colors)]
            pts = []
            for i, y in enumerate(ys, start=1):
                x, yy = xy(i, float(y))
                pts.append(f"{x:.2f},{yy:.2f}")
            if pts:
                parts.append(
                    f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{" ".join(pts)}' />"
                )
                lx = margin + idx * 120
                ly = margin - 20
                parts.append(
                    f"<rect x='{lx}' y='{ly-10}' width='12' height='12' fill='{color}' />"
                )
                parts.append(f"<text x='{lx+18}' y='{ly}' font-size='12'>{label}</text>")
        parts.append("</svg>")
        with open(os.path.join(self.results_dir, name), "w", encoding="utf-8") as f:
            f.write("\n".join(parts))

