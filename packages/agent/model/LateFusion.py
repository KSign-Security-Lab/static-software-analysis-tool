import torch
import torch.nn as nn
from torch_geometric.data import Data  # pyright: ignore[reportMissingImports]

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
    ):
        super().__init__()
        self.ast_gnn = GINEStack(
            ast_in, ast_edge_dim, hid=hid, out_dim=hid, num_layers=gnn_layers
        )
        self.dfg_gnn = GINEStack(
            dfg_in, dfg_edge_dim, hid=hid, out_dim=hid, num_layers=gnn_layers
        )
        # Build fusion MLP with configurable depth
        layers = []
        in_dim = hid * 2
        for i in range(max(1, fusion_depth)):
            out_dim_fc = hid if i < fusion_depth - 1 else out_classes
            layers.append(nn.Linear(in_dim, out_dim_fc))
            if i < fusion_depth - 1:
                layers.append(nn.ReLU())
            in_dim = out_dim_fc
        self.fc = nn.Sequential(*layers)

    def forward(self, ast_data: Data, dfg_data: Data):
        ha = self.ast_gnn(ast_data)
        hd = self.dfg_gnn(dfg_data)
        h = torch.cat([ha, hd], dim=-1)
        return self.fc(h)
