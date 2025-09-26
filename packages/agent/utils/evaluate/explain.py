"""
GNN explanation utilities module.

This module provides comprehensive explanation tools for Graph Neural Networks.
"""

import os
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.utils import to_networkx


def _safe_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _prepare_graph(
    graph: Data, device: Union[torch.device, str]
) -> Tuple[Data, torch.Tensor]:
    edge_index = getattr(graph, "edge_index", None)
    edge_attr = getattr(graph, "edge_attr", None)
    batch = getattr(graph, "batch", None)

    if isinstance(edge_index, torch.Tensor):
        edge_index = edge_index.detach().to(device)
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long, device=device)

    x = getattr(graph, "x", None)
    if isinstance(x, torch.Tensor) and x.numel() > 0:
        x = x.detach().to(device).clone().requires_grad_(True)
    else:
        if edge_index.numel() > 0:
            num_nodes = int(edge_index.max().item()) + 1
        else:
            num_nodes = int(getattr(graph, "num_nodes", 1) or 1)
        x = torch.zeros((num_nodes, 1), dtype=torch.float32, device=device)
        x.requires_grad_(True)

    data_kwargs = {"x": x, "edge_index": edge_index}
    if isinstance(edge_attr, torch.Tensor) and edge_attr.numel() > 0:
        data_kwargs["edge_attr"] = edge_attr.detach().to(device)
    if isinstance(batch, torch.Tensor) and batch.numel() == x.size(0):
        data_kwargs["batch"] = batch.detach().to(device)

    return Data(**data_kwargs), x


def _forward_model(model, ast: Optional[Data], dfg: Optional[Data]) -> torch.Tensor:
    if ast is not None and dfg is not None:
        try:
            return model(ast, dfg)  # type: ignore[misc]
        except TypeError:
            return model(ast)  # type: ignore[call-arg]
    if ast is not None:
        return model(ast)  # type: ignore[call-arg]
    if dfg is not None:
        return model(dfg)  # type: ignore[call-arg]
    raise ValueError("At least one graph must be provided for saliency computation")


def compute_node_saliency(
    model: nn.Module,
    ast_data: Optional[Data],
    dfg_data: Optional[Data],
    positive_class: int = 1,
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Return node-level and parameter-level saliency maps for the positive class."""

    device = next(model.parameters()).device
    was_training = model.training
    model.eval()

    ast_prepped = ast_x = None
    dfg_prepped = dfg_x = None

    if ast_data is not None:
        ast_prepped, ast_x = _prepare_graph(ast_data, device)
    if dfg_data is not None:
        dfg_prepped, dfg_x = _prepare_graph(dfg_data, device)

    node_saliency: Dict[str, np.ndarray] = {}
    param_saliency: Dict[str, np.ndarray] = {}

    try:
        with torch.enable_grad():
            model.zero_grad(set_to_none=True)
            if ast_x is not None and ast_x.grad is not None:
                ast_x.grad.zero_()
            if dfg_x is not None and dfg_x.grad is not None:
                dfg_x.grad.zero_()

            logits = _forward_model(model, ast_prepped, dfg_prepped)
            if logits.ndim == 1:
                target_logit = logits[positive_class]
            else:
                target_logit = logits[0, positive_class]

            target_logit.backward(retain_graph=False)

            if ast_x is not None and ast_x.grad is not None:
                node_saliency["ast"] = (
                    torch.norm(ast_x.grad, dim=1).detach().cpu().numpy()
                )
            if dfg_x is not None and dfg_x.grad is not None:
                node_saliency["dfg"] = (
                    torch.norm(dfg_x.grad, dim=1).detach().cpu().numpy()
                )

            for name, param in model.named_parameters():
                grad = param.grad
                if grad is None:
                    continue
                sal = (grad * param).abs().detach().cpu()
                if sal.ndim == 1:
                    sal = sal.unsqueeze(0)
                elif sal.ndim > 2:
                    sal = sal.view(sal.shape[0], -1)
                param_saliency[name] = sal.numpy()
    finally:
        model.zero_grad(set_to_none=True)
        if was_training:
            model.train()

    return node_saliency, param_saliency


def save_saliency_heatmap(out_dir: str, name: str, scores: np.ndarray) -> None:
    _safe_dir(out_dir)
    arr = scores
    if arr.ndim == 1:
        arr = arr[None, :]
    try:
        import matplotlib.pyplot as plt  # type: ignore

        plt.figure(figsize=(max(4, arr.shape[1] / 10), 2))
        plt.imshow(arr, aspect="auto", cmap="viridis")
        plt.yticks([])
        plt.colorbar()
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, f"{name}.png"))
        plt.close()
    except Exception:
        np.save(os.path.join(out_dir, f"{name}.npy"), arr)


def save_parameter_saliency_heatmaps(
    out_dir: str,
    param_saliencies: Dict[str, np.ndarray],
    top_k: int = 8,
) -> None:
    if not param_saliencies:
        return
    ranked = sorted(
        param_saliencies.items(), key=lambda kv: float(np.max(kv[1])), reverse=True
    )
    for name, scores in ranked[:top_k]:
        safe_name = name.replace(".", "_").replace("/", "_")
        save_saliency_heatmap(out_dir, f"param_{safe_name}", scores)


def compute_edge_importance(
    model,
    ast_data: Optional[Data],
    dfg_data: Optional[Data],
    positive_class: int = 1,
) -> Dict[str, np.ndarray]:
    """Compute edge-level importance scores for graph edges."""
    device = next(model.parameters()).device
    was_training = model.training
    model.eval()

    edge_importance = {}

    try:
        with torch.enable_grad():
            # Clone and prepare data
            if ast_data is not None:
                ast_data = ast_data.clone().to(device)
                if ast_data.edge_attr is not None:
                    ast_data.edge_attr.requires_grad_(True)

            if dfg_data is not None:
                dfg_data = dfg_data.clone().to(device)
                if dfg_data.edge_attr is not None:
                    dfg_data.edge_attr.requires_grad_(True)

            # Forward pass
            if ast_data is not None and dfg_data is not None:
                logits = model(ast_data, dfg_data)
            elif ast_data is not None:
                logits = model(ast_data)
            elif dfg_data is not None:
                logits = model(dfg_data)
            else:
                raise ValueError("At least one graph must be provided")

            # Backward pass
            if logits.ndim == 1:
                target_logit = logits[positive_class]
            else:
                target_logit = logits[0, positive_class]

            target_logit.backward(retain_graph=True)

            # Extract edge importance for AST
            if (
                ast_data is not None
                and ast_data.edge_attr is not None
                and ast_data.edge_attr.grad is not None
            ):
                edge_importance["ast"] = (
                    torch.norm(ast_data.edge_attr.grad, dim=1).detach().cpu().numpy()
                )

            # Extract edge importance for DFG
            if (
                dfg_data is not None
                and dfg_data.edge_attr is not None
                and dfg_data.edge_attr.grad is not None
            ):
                edge_importance["dfg"] = (
                    torch.norm(dfg_data.edge_attr.grad, dim=1).detach().cpu().numpy()
                )

    finally:
        if was_training:
            model.train()

    return edge_importance


def analyze_decision_rationale(
    model,
    ast_data: Optional[Data],
    dfg_data: Optional[Data],
    positive_class: int = 1,
    top_k_nodes: int = 10,
    top_k_edges: int = 10,
) -> Dict[str, Union[Dict, List, np.ndarray]]:
    """
    Comprehensive analysis of GNN decision rationale including:
    - Most important nodes and edges
    - Graph structure analysis
    - Decision confidence and reasoning
    """
    device = next(model.parameters()).device
    was_training = model.training
    model.eval()

    rationale = {
        "prediction": None,
        "confidence": None,
        "top_nodes": {},
        "top_edges": {},
        "graph_stats": {},
        "decision_path": {},
        "feature_importance": {},
    }

    try:
        # Get prediction and confidence
        with torch.no_grad():
            if ast_data is not None and dfg_data is not None:
                logits = model(ast_data, dfg_data)
            elif ast_data is not None:
                logits = model(ast_data)
            elif dfg_data is not None:
                logits = model(dfg_data)
            else:
                raise ValueError("At least one graph must be provided")

            probs = F.softmax(logits, dim=-1)
            prediction = logits.argmax(dim=-1).item()
            confidence = probs[0, prediction].item()

            rationale["prediction"] = int(prediction)
            rationale["confidence"] = float(confidence)

        # Compute node and edge importance
        node_saliency, param_saliency = compute_node_saliency(
            model, ast_data, dfg_data, positive_class
        )
        edge_importance = compute_edge_importance(
            model, ast_data, dfg_data, positive_class
        )

        # Debug: print edge importance keys
        print(f"DEBUG: edge_importance keys: {list(edge_importance.keys())}")
        for key, value in edge_importance.items():
            print(
                f"DEBUG: {key} edge importance shape: {value.shape if hasattr(value, 'shape') else type(value)}"
            )

        # Ensure both AST and DFG edges are included
        if "dfg" not in edge_importance:
            print("DEBUG: Adding empty DFG edge importance")
            edge_importance["dfg"] = np.array([])

        # Analyze top nodes - only keep top 1
        for graph_type, scores in node_saliency.items():
            if len(scores) > 0:
                top_indices = np.argsort(scores)[-1:][::-1]  # Only top 1
                rationale["top_nodes"][graph_type] = {
                    "top_node_index": int(top_indices[0]),
                    "top_node_score": float(scores[top_indices[0]]),
                    "mean_score": float(np.mean(scores)),
                    "max_score": float(np.max(scores)),
                }
            else:
                # If no node importance scores, create empty entry
                rationale["top_nodes"][graph_type] = {
                    "top_node_index": None,
                    "top_node_score": 0.0,
                    "mean_score": 0.0,
                    "max_score": 0.0,
                }

        # Analyze top edges - only keep top 1
        for graph_type in ["ast", "dfg"]:
            if graph_type in edge_importance and len(edge_importance[graph_type]) > 0:
                scores = edge_importance[graph_type]
                top_indices = np.argsort(scores)[-1:][::-1]  # Only top 1
                rationale["top_edges"][graph_type] = {
                    "top_edge_index": int(top_indices[0]),
                    "top_edge_score": float(scores[top_indices[0]]),
                    "mean_score": float(np.mean(scores)),
                    "max_score": float(np.max(scores)),
                }
            else:
                # If no edge importance scores, create empty entry
                rationale["top_edges"][graph_type] = {
                    "top_edge_index": None,
                    "top_edge_score": 0.0,
                    "mean_score": 0.0,
                    "max_score": 0.0,
                }

        # Graph structure analysis
        for graph_type, graph_data in [("ast", ast_data), ("dfg", dfg_data)]:
            if graph_data is not None:
                rationale["graph_stats"][graph_type] = _analyze_graph_structure(
                    graph_data
                )

        # Decision path analysis
        rationale["decision_path"] = _analyze_decision_path(
            model, ast_data, dfg_data, positive_class
        )

        # Feature importance analysis
        rationale["feature_importance"] = _analyze_feature_importance(param_saliency)

    finally:
        if was_training:
            model.train()

    return rationale


def _analyze_graph_structure(graph_data: Data) -> Dict[str, Union[int, float, List]]:
    """Analyze basic graph structure statistics."""
    stats = {}

    if hasattr(graph_data, "x") and graph_data.x is not None:
        stats["num_nodes"] = int(graph_data.x.size(0))
        stats["num_features"] = int(graph_data.x.size(1))

    if hasattr(graph_data, "edge_index") and graph_data.edge_index is not None:
        stats["num_edges"] = int(graph_data.edge_index.size(1))

        # Convert to NetworkX for advanced analysis
        try:
            G = to_networkx(graph_data, to_undirected=True)
            stats["density"] = float(nx.density(G))
            stats["num_connected_components"] = int(nx.number_connected_components(G))

            if nx.number_connected_components(G) > 0:
                largest_cc = max(nx.connected_components(G), key=len)
                stats["largest_component_size"] = len(largest_cc)
                stats["largest_component_ratio"] = len(largest_cc) / stats["num_nodes"]
            else:
                stats["largest_component_size"] = 0
                stats["largest_component_ratio"] = 0.0

        except Exception:
            stats["density"] = 0.0
            stats["num_connected_components"] = 1
            stats["largest_component_size"] = stats["num_nodes"]
            stats["largest_component_ratio"] = 1.0

    return stats


def _analyze_decision_path(
    model,
    ast_data: Optional[Data],
    dfg_data: Optional[Data],
    positive_class: int = 1,
) -> Dict[str, Any]:
    """Analyze the decision path through the model layers."""
    device = next(model.parameters()).device
    was_training = model.training
    model.eval()

    decision_path = {
        "layer_activations": {},
        "attention_weights": {},
        "gradient_flow": {},
    }

    try:
        # Hook to capture intermediate activations
        activations = {}

        def hook_fn(name):
            def hook(module, input, output):
                activations[name] = output.detach()

            return hook

        # Register hooks for GNN layers
        hooks = []
        for name, module in model.named_modules():
            if hasattr(module, "forward") and "conv" in name.lower():
                hook = module.register_forward_hook(hook_fn(name))
                hooks.append(hook)

        # Forward pass
        with torch.enable_grad():
            if ast_data is not None and dfg_data is not None:
                logits = model(ast_data, dfg_data)
            elif ast_data is not None:
                logits = model(ast_data)
            elif dfg_data is not None:
                logits = model(dfg_data)
            else:
                return decision_path

            # Store activations
            for name, activation in activations.items():
                if isinstance(activation, torch.Tensor):
                    decision_path["layer_activations"][name] = {
                        "shape": list(activation.shape),
                        "mean": float(activation.mean().item()),
                        "std": float(activation.std().item()),
                        "max": float(activation.max().item()),
                        "min": float(activation.min().item()),
                    }

        # Clean up hooks
        for hook in hooks:
            hook.remove()

    finally:
        if was_training:
            model.train()

    return decision_path


def _analyze_feature_importance(
    param_saliency: Dict[str, np.ndarray],
) -> Dict[str, Any]:
    """Analyze feature importance from parameter saliency."""
    feature_importance = {
        "layer_importance": {},
        "parameter_importance": {},
        "overall_importance": {},
    }

    if not param_saliency:
        return feature_importance

    # Analyze by layer
    layer_importance = {}
    for param_name, saliency in param_saliency.items():
        layer_name = param_name.split(".")[0] if "." in param_name else "root"

        if layer_name not in layer_importance:
            layer_importance[layer_name] = []

        layer_importance[layer_name].append(float(np.max(saliency)))

    # Compute layer importance scores
    for layer, scores in layer_importance.items():
        feature_importance["layer_importance"][layer] = {
            "max_importance": float(np.max(scores)),
            "mean_importance": float(np.mean(scores)),
            "total_importance": float(np.sum(scores)),
        }

    # Overall parameter ranking
    param_scores = [(name, float(np.max(sal))) for name, sal in param_saliency.items()]
    param_scores.sort(key=lambda x: x[1], reverse=True)

    feature_importance["parameter_importance"] = {
        "top_parameters": param_scores[:10],
        "total_parameters": len(param_scores),
    }

    return feature_importance


def convert_rationale_to_human_friendly(
    rationale: Dict[str, Union[Dict, List, np.ndarray]],
    ast_data: Optional[Data] = None,
    dfg_data: Optional[Data] = None,
    original_sample: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert technical rationale to human-friendly format using original data."""

    human_rationale = {
        "prediction": rationale.get("prediction"),
        "confidence": rationale.get("confidence"),
        "top_nodes": {},
        "top_edges": {},
        "graph_stats": rationale.get("graph_stats", {}),
        "decision_path": rationale.get("decision_path", {}),
        "feature_importance": rationale.get("feature_importance", {}),
    }

    # Convert AST top nodes to human-friendly format
    top_nodes = rationale.get("top_nodes", {})
    if isinstance(top_nodes, dict) and "ast" in top_nodes:
        ast_nodes = top_nodes.get("ast", {})
        human_rationale["top_nodes"]["ast"] = {
            "top_node_details": None,
        }

        # Add top node details if we have the original data
        if ast_data is not None and ast_nodes.get("top_node_index") is not None:
            idx = ast_nodes.get("top_node_index")
            if idx is not None and ast_data.x is not None and idx < ast_data.x.size(0):
                node_features = ast_data.x[idx].tolist()

                # Try to get original node data
                if original_sample and "ast_result_original_nodes" in original_sample:
                    original_nodes = original_sample["ast_result_original_nodes"]
                    if idx < len(original_nodes):
                        # Include the full node data structure with importance score
                        full_node_data = original_nodes[idx]
                        full_node_data["importance_score"] = ast_nodes.get(
                            "top_node_score", 0.0
                        )
                        human_rationale["top_nodes"]["ast"][
                            "top_node_details"
                        ] = full_node_data
                    else:
                        # Fallback if index out of range
                        human_rationale["top_nodes"]["ast"]["top_node_details"] = {
                            "node_id": int(idx),
                            "importance_score": ast_nodes.get("top_node_score", 0.0),
                            "features": node_features,
                        }
                else:
                    # Fallback to PyG data only
                    human_rationale["top_nodes"]["ast"]["top_node_details"] = {
                        "node_id": int(idx),
                        "importance_score": ast_nodes.get("top_node_score", 0.0),
                        "features": node_features,
                    }

    # Convert DFG top nodes to human-friendly format
    if isinstance(top_nodes, dict) and "dfg" in top_nodes:
        dfg_nodes = top_nodes.get("dfg", {})
        human_rationale["top_nodes"]["dfg"] = {
            "top_node_details": None,
        }

        # Add top node details if we have the original data
        if dfg_data is not None and dfg_nodes.get("top_node_index") is not None:
            idx = dfg_nodes.get("top_node_index")
            if idx is not None and dfg_data.x is not None and idx < dfg_data.x.size(0):
                node_features = dfg_data.x[idx].tolist()

                # Try to get original node data
                if original_sample and "dfg_result_original_nodes" in original_sample:
                    original_nodes = original_sample["dfg_result_original_nodes"]
                    if idx < len(original_nodes):
                        # Include the full node data structure with importance score
                        full_node_data = original_nodes[idx]
                        full_node_data["importance_score"] = dfg_nodes.get(
                            "top_node_score", 0.0
                        )
                        human_rationale["top_nodes"]["dfg"][
                            "top_node_details"
                        ] = full_node_data
                    else:
                        # Fallback if index out of range
                        human_rationale["top_nodes"]["dfg"]["top_node_details"] = {
                            "node_id": int(idx),
                            "importance_score": dfg_nodes.get("top_node_score", 0.0),
                            "features": node_features,
                        }
                else:
                    # Fallback to PyG data only
                    human_rationale["top_nodes"]["dfg"]["top_node_details"] = {
                        "node_id": int(idx),
                        "importance_score": dfg_nodes.get("top_node_score", 0.0),
                        "features": node_features,
                    }

    # Convert edge information to human-friendly format
    top_edges = rationale.get("top_edges", {})
    if isinstance(top_edges, dict) and "ast" in top_edges:
        ast_edges = top_edges.get("ast", {})
        human_rationale["top_edges"]["ast"] = {
            "top_edge_details": None,
        }

        if ast_data is not None and ast_edges.get("top_edge_index") is not None:
            edge_idx = ast_edges.get("top_edge_index")
            if (
                edge_idx is not None
                and ast_data.edge_index is not None
                and edge_idx < ast_data.edge_index.size(1)
            ):
                src, dst = ast_data.edge_index[:, edge_idx].tolist()
                edge_attr = (
                    ast_data.edge_attr[edge_idx].tolist()
                    if ast_data.edge_attr is not None
                    else [0.0]
                )

                # Try to get original edge data
                if original_sample and "ast_result_original_edges" in original_sample:
                    original_edges = original_sample["ast_result_original_edges"]
                    if edge_idx < len(original_edges):
                        # Include the full edge data with importance score
                        full_edge_data = original_edges[edge_idx]
                        if isinstance(full_edge_data, dict):
                            full_edge_data["importance_score"] = ast_edges.get(
                                "top_edge_score", 0.0
                            )
                            full_edge_data["source_node"] = int(src)
                            full_edge_data["destination_node"] = int(dst)
                            human_rationale["top_edges"]["ast"][
                                "top_edge_details"
                            ] = full_edge_data
                        else:
                            # Handle list format
                            human_rationale["top_edges"]["ast"]["top_edge_details"] = {
                                "edge_data": full_edge_data,
                                "source_node": int(src),
                                "destination_node": int(dst),
                                "importance_score": ast_edges.get(
                                    "top_edge_score", 0.0
                                ),
                            }
                    else:
                        # Fallback
                        human_rationale["top_edges"]["ast"]["top_edge_details"] = {
                            "source_node": int(src),
                            "destination_node": int(dst),
                            "importance_score": ast_edges.get("top_edge_score", 0.0),
                            "edge_attributes": edge_attr,
                        }
                else:
                    # Fallback
                    human_rationale["top_edges"]["ast"]["top_edge_details"] = {
                        "source_node": int(src),
                        "destination_node": int(dst),
                        "importance_score": ast_edges.get("top_edge_score", 0.0),
                        "edge_attributes": edge_attr,
                    }

    if isinstance(top_edges, dict) and "dfg" in top_edges:
        dfg_edges = top_edges.get("dfg", {})
        human_rationale["top_edges"]["dfg"] = {
            "top_edge_details": None,
        }

        if dfg_data is not None and dfg_edges.get("top_edge_index") is not None:
            edge_idx = dfg_edges.get("top_edge_index")
            if (
                edge_idx is not None
                and dfg_data.edge_index is not None
                and edge_idx < dfg_data.edge_index.size(1)
            ):
                src, dst = dfg_data.edge_index[:, edge_idx].tolist()
                edge_attr = (
                    dfg_data.edge_attr[edge_idx].tolist()
                    if dfg_data.edge_attr is not None
                    else [0.0]
                )

                # Try to get original edge data
                if original_sample and "dfg_result_original_edges" in original_sample:
                    original_edges = original_sample["dfg_result_original_edges"]
                    if edge_idx < len(original_edges):
                        # Include the full edge data with importance score
                        full_edge_data = original_edges[edge_idx]
                        if isinstance(full_edge_data, dict):
                            full_edge_data["importance_score"] = dfg_edges.get(
                                "top_edge_score", 0.0
                            )
                            full_edge_data["source_node"] = int(src)
                            full_edge_data["destination_node"] = int(dst)
                            human_rationale["top_edges"]["dfg"][
                                "top_edge_details"
                            ] = full_edge_data
                        else:
                            # Handle list format
                            human_rationale["top_edges"]["dfg"]["top_edge_details"] = {
                                "edge_data": full_edge_data,
                                "source_node": int(src),
                                "destination_node": int(dst),
                                "importance_score": dfg_edges.get(
                                    "top_edge_score", 0.0
                                ),
                            }
                    else:
                        # Fallback
                        human_rationale["top_edges"]["dfg"]["top_edge_details"] = {
                            "source_node": int(src),
                            "destination_node": int(dst),
                            "importance_score": dfg_edges.get("top_edge_score", 0.0),
                            "edge_attributes": edge_attr,
                        }
                else:
                    # Fallback
                    human_rationale["top_edges"]["dfg"]["top_edge_details"] = {
                        "source_node": int(src),
                        "destination_node": int(dst),
                        "importance_score": dfg_edges.get("top_edge_score", 0.0),
                        "edge_attributes": edge_attr,
                    }

    # Add original sample metadata if available
    if original_sample is not None:
        human_rationale["sample_metadata"] = {
            "filename": original_sample.get("file"),
            "path": original_sample.get("path"),
            "true_label": original_sample.get("label"),
            "predicted_label": original_sample.get("predicted_label"),
            "confidence": original_sample.get("confidence"),
        }

    return human_rationale


def save_decision_rationale(
    out_dir: str,
    rationale: Dict[str, Union[Dict, List, np.ndarray]],
    sample_id: str = "sample",
    ast_data: Optional[Data] = None,
    dfg_data: Optional[Data] = None,
    original_sample: Optional[Dict[str, Any]] = None,
) -> None:
    """Save decision rationale analysis to files."""
    _safe_dir(out_dir)

    # Convert to human-friendly format
    human_rationale = convert_rationale_to_human_friendly(
        rationale, ast_data, dfg_data, original_sample
    )

    # Save as JSON
    import json

    # Convert numpy arrays and tensors to lists for JSON serialization
    def convert_numpy(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif hasattr(obj, "tolist"):  # PyTorch tensors
            try:
                return obj.tolist()
            except:
                return str(obj)
        elif hasattr(obj, "item"):  # Single value tensors
            try:
                return obj.item()
            except:
                return str(obj)
        elif hasattr(obj, "detach"):  # PyTorch tensors without tolist
            try:
                return obj.detach().cpu().numpy().tolist()
            except:
                return str(obj)
        elif isinstance(obj, dict):
            return {k: convert_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(convert_numpy(item) for item in obj)
        else:
            return obj

    rationale_json = convert_numpy(human_rationale)

    with open(os.path.join(out_dir, f"{sample_id}_rationale.json"), "w") as f:
        json.dump(rationale_json, f, indent=2)

    # Save node importance plots
    top_nodes = rationale.get("top_nodes", {})
    if isinstance(top_nodes, dict):
        for graph_type, node_data in top_nodes.items():
            if isinstance(node_data, dict) and "scores" in node_data:
                save_saliency_heatmap(
                    out_dir,
                    f"{sample_id}_{graph_type}_top_nodes",
                    np.array(node_data["scores"]),
                )

    # Save edge importance plots
    top_edges = rationale.get("top_edges", {})
    if isinstance(top_edges, dict):
        for graph_type, edge_data in top_edges.items():
            if isinstance(edge_data, dict) and "scores" in edge_data:
                save_saliency_heatmap(
                    out_dir,
                    f"{sample_id}_{graph_type}_top_edges",
                    np.array(edge_data["scores"]),
                )


def _build_pyg_from_ast_item(ast_item) -> Data:
    """Build a PyG Data from an AST graph dict with keys: nodes, edges_ast_pc."""
    from torch_geometric.data import Data

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


def _build_pyg_from_dfg_item(dfg_item) -> Data:
    """Build a PyG Data from a DFG graph dict with keys: nodes, edges."""
    from torch_geometric.data import Data

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


def batch_explain_decisions(
    model,
    dataloader,
    device: torch.device,
    output_dir: str,
    max_samples: int = 100,
    mode: str = "both",
) -> Dict[str, List]:
    """
    Explain decisions for a batch of samples from a dataloader.
    Returns aggregated explanation statistics.
    """
    model.eval()
    explanations = []
    all_predictions = []
    all_confidences = []

    _safe_dir(output_dir)

    sample_count = 0

    with torch.no_grad():
        for batch_idx, batch in enumerate(dataloader):
            if sample_count >= max_samples:
                break

            B = len(batch["label"])

            for i in range(B):
                if sample_count >= max_samples:
                    break

                # Prepare data based on mode
                ast_data = None
                dfg_data = None

                if mode in ["both", "ast"]:
                    ast_data = _build_pyg_from_ast_item(batch["ast_graph"][i]).to(
                        str(device)
                    )
                if mode in ["both", "dfg"]:
                    dfg_data = _build_pyg_from_dfg_item(batch["dfg_graph"][i]).to(
                        str(device)
                    )

                # Get prediction
                if ast_data is not None and dfg_data is not None:
                    logits = model(ast_data, dfg_data)
                elif ast_data is not None:
                    logits = model(ast_data)
                elif dfg_data is not None:
                    logits = model(dfg_data)
                else:
                    continue

                probs = F.softmax(logits, dim=-1)
                prediction = logits.argmax(dim=-1).item()
                confidence = probs[0, prediction].item()

                all_predictions.append(prediction)
                all_confidences.append(confidence)

                # Generate explanation
                rationale = analyze_decision_rationale(
                    model, ast_data, dfg_data, positive_class=1
                )

                explanations.append(rationale)

                # Save individual explanation
                save_decision_rationale(
                    output_dir, rationale, f"sample_{sample_count:04d}"
                )

                sample_count += 1

    # Aggregate statistics
    aggregated = {
        "total_samples": len(explanations),
        "predictions": all_predictions,
        "confidences": all_confidences,
        "avg_confidence": float(np.mean(all_confidences)) if all_confidences else 0.0,
        "prediction_distribution": {
            "class_0": all_predictions.count(0),
            "class_1": all_predictions.count(1),
        },
    }

    # Save aggregated results
    import json

    with open(os.path.join(output_dir, "aggregated_explanations.json"), "w") as f:
        json.dump(aggregated, f, indent=2)

    return aggregated
