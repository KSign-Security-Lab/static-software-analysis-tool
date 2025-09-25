from typing import Optional

import torch
import torch.nn as nn
from torch_geometric.data import Data

from .GNN import GINEStack


class LateFusionModel(nn.Module):
    def __init__(
        self,
        ast_in: int,
        ast_edge_dim: int,
        dfg_in: int,
        dfg_edge_dim: int,
        hid: int = 64,
        out_classes: int = 2,
        gnn_layers: int = 5,
        fusion_depth: int = 3,
        use_ast: bool = True,
        use_dfg: bool = True,
    ):
        super().__init__()
        self.use_ast = use_ast
        self.use_dfg = use_dfg

        self.ast_gnn = (
            GINEStack(ast_in, ast_edge_dim, hid=hid, out_dim=hid, num_layers=gnn_layers)
            if use_ast
            else None
        )
        self.dfg_gnn = (
            GINEStack(dfg_in, dfg_edge_dim, hid=hid, out_dim=hid, num_layers=gnn_layers)
            if use_dfg
            else None
        )
        # Build fusion MLP with configurable depth
        layers = []
        in_dim = hid * ((1 if use_ast else 0) + (1 if use_dfg else 0))
        if in_dim == 0:
            in_dim = hid  # fallback to avoid zero-dim linear
        for i in range(max(1, fusion_depth)):
            out_dim_fc = hid if i < fusion_depth - 1 else out_classes
            layers.append(nn.Linear(in_dim, out_dim_fc))
            if i < fusion_depth - 1:
                layers.append(nn.ReLU())
            in_dim = out_dim_fc
        self.fc = nn.Sequential(*layers)

    def forward(self, ast_data: Optional[Data], dfg_data: Optional[Data]):
        reps = []
        if self.use_ast and self.ast_gnn is not None and ast_data is not None:
            reps.append(self.ast_gnn(ast_data))
        if self.use_dfg and self.dfg_gnn is not None and dfg_data is not None:
            reps.append(self.dfg_gnn(dfg_data))
        if not reps:
            # Create a zero representation on the same device as the FC layer
            first_layer = self.fc[0] if len(self.fc) > 0 else None
            in_features = (
                first_layer.in_features if isinstance(first_layer, nn.Linear) else 1
            )
            model_device = next(self.fc.parameters()).device
            reps = [torch.zeros((1, int(in_features)), device=model_device)]
        h = reps[0] if len(reps) == 1 else torch.cat(reps, dim=-1)
        return self.fc(h)
