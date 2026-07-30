import json
import os
from typing import Any, Dict, Optional
from collections import defaultdict

import numpy as np
import torch
from torch.utils.data import DataLoader as TorchDataLoader
from torch_geometric.data import Batch


from .train import forward_by_mode


from .model.SingleBranch import ASTOnlyModel, DFGOnlyModel
from .model.LateFusion import LateFusionModel


# Small helper to appease type checkers for torch-geometric Batch/Data `.to`.
def _move_to_device(obj: object, device: torch.device):
    try:  # runtime has .to for Data/Batch
        return getattr(obj, "to")(device)  # type: ignore[no-any-return]
    except Exception:
        return obj


def latest_epoch_checkpoint(results_dir: str) -> Optional[str]:
    try:
        files = [
            os.path.join(results_dir, f)
            for f in os.listdir(results_dir)
            if f.startswith("model_epoch_") and f.endswith(".pt")
        ]
    except FileNotFoundError:
        files = []
    if not files:
        return None

    def epoch_num(p: str) -> int:
        try:
            name = os.path.basename(p)
            return int(name.split("model_epoch_")[1].split(".pt")[0])
        except Exception:
            return -1

    return max(files, key=epoch_num)


def infer_mode_from_model(model: torch.nn.Module) -> str:
    if isinstance(model, ASTOnlyModel):
        return "ast"
    if isinstance(model, DFGOnlyModel):
        return "dfg"
    if isinstance(model, LateFusionModel):
        return "late_fusion"
    return "both"


def load_model_robust(model_path: str, device: torch.device) -> torch.nn.Module:
    """Load a serialized model object (full checkpoint).

    This avoids relying on saved training configs. If a state_dict-only file is
    provided, raise a clear error indicating a full-model checkpoint is needed.
    """
    obj = torch.load(model_path, map_location=device, weights_only=False)
    if isinstance(obj, torch.nn.Module):
        obj.to(device)
        return obj
    raise RuntimeError(
        "Checkpoint contains only a state_dict. Please use a full-model epoch checkpoint (model_epoch_*.pt)."
    )


def evaluate_full_dataset(
    model: torch.nn.Module,
    dataloader: TorchDataLoader,
    device: torch.device,
    mode: str,
    *,
    forward_fn=None,
) -> Dict[str, Any]:
    model.eval()
    total = 0
    correct = 0
    confidences: list[float] = []

    with torch.no_grad():
        for batch in dataloader:
            y = batch["y"].to(device)
            if forward_fn is None:
                logits = forward_by_mode(model, batch, device, mode)
            else:
                logits = forward_fn(model, batch, device, mode)
            probs = torch.softmax(logits, dim=-1)
            pred = probs.argmax(dim=-1)
            total += int(y.numel())
            correct += int((pred == y).sum().item())
            confidences.extend(probs.max(dim=-1).values.detach().cpu().tolist())

    accuracy = correct / total if total > 0 else 0.0

    return {
        "evaluation_summary": {
            "total_samples": total,
            "accuracy": accuracy,
            "correct_predictions": correct,
            "incorrect_predictions": total - correct,
        },
        "per_class_statistics": {},
        "misclassified_samples": [],
        "filename_availability": {
            "samples_with_filenames": 0,
            "samples_with_function_names": 0,
            "total_samples": total,
        },
    }


def analyze_sample_with_model(
    model: torch.nn.Module,
    sample: Dict[str, Any],
    sample_id: str,
    device: torch.device,
    *,
    mode: Optional[str] = None,
    forward_fn=None,
) -> Dict[str, Any]:
    filename = sample.get("file") or sample.get("path") or sample.get("filename")
    function_name = sample.get("function") or sample.get("function_name")
    if filename and not function_name:
        function_name = os.path.splitext(os.path.basename(filename))[0]

    ast_data = sample.get("ast_graph")
    dfg_data = sample.get("dfg_graph")

    # Wrap per-sample Data into a Batch to satisfy batched forward signatures
    ast_b = _move_to_device(Batch.from_data_list([ast_data]), device) if ast_data is not None else None
    dfg_b = _move_to_device(Batch.from_data_list([dfg_data]), device) if dfg_data is not None else None

    model.eval()
    with torch.no_grad():
        if forward_fn is not None and mode is not None:
            single_batch = {"y": sample.get("y", torch.tensor(0))}
            if ast_b is not None:
                single_batch["ast_graph"] = ast_b
            if dfg_b is not None:
                single_batch["dfg_graph"] = dfg_b
            logits = forward_fn(model, single_batch, device, mode)
        else:
            # Respect explicit mode when deciding inputs
            if mode == "ast":
                if ast_b is None:
                    raise ValueError("AST mode requires ast_graph data")
                logits = model(ast_b)
            elif mode == "dfg":
                if dfg_b is None:
                    raise ValueError("DFG mode requires dfg_graph data")
                logits = model(dfg_b)
            else:
                # both/late_fusion
                if ast_b is not None and dfg_b is not None:
                    logits = model(ast_b, dfg_b)
                elif ast_b is not None:
                    logits = model(ast_b)
                elif dfg_b is not None:
                    logits = model(dfg_b)
                else:
                    raise ValueError("No valid graph data available")

        probs = torch.softmax(logits, dim=-1)
        predicted_label = int(torch.argmax(logits, dim=-1).item())
        confidence = float(probs[0, predicted_label].item())

    true_label = sample.get("y", 0)
    if isinstance(true_label, torch.Tensor):
        true_label = int(true_label.item())
    else:
        true_label = int(true_label)

    return {
        "sample_id": sample_id,
        "filename": filename,
        "function_name": function_name,
        "true_label": true_label,
        "predicted_label": predicted_label,
        "confidence": confidence,
        "correct_prediction": (true_label == predicted_label),
        "ast_data": ast_data,
        "dfg_data": dfg_data,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Evaluation loop
# ──────────────────────────────────────────────────────────────────────────────
def evaluate_model(
    model: torch.nn.Module,
    dataloader: TorchDataLoader,
    device: torch.device,
    mode: str,
    max_samples: int = 100,
    output_dir: Optional[str] = None,
    *,
    forward_fn=None,
) -> Dict[str, Any]:
    model.eval()
    sample_results = []
    classification_files = defaultdict(list)
    classification_functions = defaultdict(list)
    sample_count = 0

    # no stdout logging here; only save results

    with torch.no_grad():
        for _, batch in enumerate(dataloader):
            if sample_count >= max_samples:
                break

            B = int(batch["y"].shape[0])
            for i in range(B):
                if sample_count >= max_samples:
                    break

                sample_id = f"sample_{sample_count:04d}"
                sample = {"y": batch["y"][i]}
                if "ast_graph" in batch:
                    sample["ast_graph"] = batch["ast_graph"][i]
                if "dfg_graph" in batch:
                    sample["dfg_graph"] = batch["dfg_graph"][i]

                for meta_key in ("file", "path", "function", "function_name"):
                    if meta_key in batch and i < len(batch[meta_key]):
                        sample[meta_key] = batch[meta_key][i]

                result = analyze_sample_with_model(
                    model,
                    sample,
                    sample_id,
                    device,
                    mode=mode,
                    forward_fn=forward_fn,
                )
                sample_results.append(result)

                if result["filename"]:
                    classification_files[result["predicted_label"]].append(result["filename"])
                if result["function_name"]:
                    classification_functions[result["predicted_label"]].append(result["function_name"])

                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    sample_dir = os.path.join(output_dir, sample_id)
                    os.makedirs(sample_dir, exist_ok=True)

                    # metadata.json
                    metadata = {
                        "sample_id": sample_id,
                        "filename": result["filename"],
                        "function_name": result["function_name"],
                        "true_label": result["true_label"],
                        "predicted_label": result["predicted_label"],
                        "confidence": result["confidence"],
                        "correct_prediction": result["correct_prediction"],
                    }
                    with open(os.path.join(sample_dir, "metadata.json"), "w") as f:
                        json.dump(metadata, f, indent=2)

                    # graphs.json
                    def serialize_graph(g):
                        if g is None:
                            return None
                        return {
                            "x": g.x.detach().cpu().tolist() if hasattr(g, "x") else [],
                            "edge_index": (g.edge_index.detach().cpu().tolist() if hasattr(g, "edge_index") else []),
                            "edge_attr": (
                                g.edge_attr.detach().cpu().tolist()
                                if hasattr(g, "edge_attr") and g.edge_attr is not None
                                else []
                            ),
                            "x_feature_names": getattr(g, "x_feature_names", None),
                            "edge_feature_names": getattr(g, "edge_feature_names", None),
                        }

                    graphs_payload = {
                        "ast_graph": serialize_graph(sample.get("ast_graph")),
                        "dfg_graph": serialize_graph(sample.get("dfg_graph")),
                    }
                    with open(os.path.join(sample_dir, "graphs.json"), "w") as f:
                        json.dump(graphs_payload, f, indent=2)

                sample_count += 1

    if not sample_results:
        return {"error": "No samples processed"}

    total_samples = len(sample_results)
    correct_predictions = sum(1 for r in sample_results if r["correct_prediction"])
    accuracy = correct_predictions / total_samples if total_samples > 0 else 0.0

    true_label_counts = defaultdict(int)
    predicted_label_counts = defaultdict(int)
    for r in sample_results:
        true_label_counts[r["true_label"]] += 1
        predicted_label_counts[r["predicted_label"]] += 1

    # Binary confusion counts (0 = negative, 1 = positive)
    tn = tp = fp = fn = 0
    for r in sample_results:
        t = int(r["true_label"]) if r.get("true_label") is not None else 0
        p = int(r["predicted_label"]) if r.get("predicted_label") is not None else 0
        if t == 1 and p == 1:
            tp += 1
        elif t == 0 and p == 0:
            tn += 1
        elif t == 0 and p == 1:
            fp += 1
        elif t == 1 and p == 0:
            fn += 1

    class_stats = {}
    all_classes = set(true_label_counts.keys()) | set(predicted_label_counts.keys())
    for c in all_classes:
        class_samples = [r for r in sample_results if r["predicted_label"] == c]
        class_conf = [r["confidence"] for r in class_samples]
        class_stats[c] = {
            "count": len(class_samples),
            "avg_confidence": float(np.mean(class_conf)) if class_conf else 0.0,
            "min_confidence": float(np.min(class_conf)) if class_conf else 0.0,
            "max_confidence": float(np.max(class_conf)) if class_conf else 0.0,
            "filenames": classification_files[c],
            "function_names": classification_functions[c],
        }

    misclassified = [
        {
            "sample_id": r["sample_id"],
            "filename": r["filename"],
            "function_name": r["function_name"],
            "true_label": r["true_label"],
            "predicted_label": r["predicted_label"],
            "confidence": r["confidence"],
        }
        for r in sample_results
        if not r["correct_prediction"]
    ]
    misclassified.sort(key=lambda x: x["confidence"], reverse=True)

    summary = {
        "evaluation_summary": {
            "total_samples": total_samples,
            "accuracy": accuracy,
            "correct_predictions": correct_predictions,
            "incorrect_predictions": total_samples - correct_predictions,
        },
        "classification_distribution": {
            "true_labels": dict(true_label_counts),
            "predicted_labels": dict(predicted_label_counts),
        },
        "confusion": {"tn": tn, "tp": tp, "fp": fp, "fn": fn},
        "per_class_statistics": {str(c): s for c, s in class_stats.items()},
        "misclassified_samples": misclassified[:20],
        "filename_availability": {
            "samples_with_filenames": sum(1 for r in sample_results if r["filename"]),
            "samples_with_function_names": sum(1 for r in sample_results if r["function_name"]),
            "total_samples": total_samples,
        },
    }
    return summary
