import os
from typing import Dict, Optional, Tuple

import numpy as np
import torch
from torch_geometric.data import Data


def _safe_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _prepare_graph(graph: Data, device: torch.device) -> Tuple[Data, torch.Tensor]:
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
    model,
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
                node_saliency["ast"] = torch.norm(ast_x.grad, dim=1).detach().cpu().numpy()
            if dfg_x is not None and dfg_x.grad is not None:
                node_saliency["dfg"] = torch.norm(dfg_x.grad, dim=1).detach().cpu().numpy()

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
