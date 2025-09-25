import torch
import torch.nn as nn
from torch_geometric.data import Data

from .GNN import GINEStack


class ASTOnlyModel(nn.Module):
    def __init__(
        self,
        ast_in: int,
        ast_edge_dim: int,
        hid: int = 64,
        out_classes: int = 2,
        gnn_layers: int = 5,
    ):
        super().__init__()
        self.gnn = GINEStack(
            ast_in, ast_edge_dim, hid=hid, out_dim=hid, num_layers=gnn_layers
        )
        self.fc = nn.Linear(hid, out_classes)

    def forward(self, ast_data: Data) -> torch.Tensor:
        h = self.gnn(ast_data)
        return self.fc(h)


class DFGOnlyModel(nn.Module):
    def __init__(
        self,
        dfg_in: int,
        dfg_edge_dim: int,
        hid: int = 64,
        out_classes: int = 2,
        gnn_layers: int = 5,
    ):
        super().__init__()
        self.gnn = GINEStack(
            dfg_in, dfg_edge_dim, hid=hid, out_dim=hid, num_layers=gnn_layers
        )
        self.fc = nn.Linear(hid, out_classes)

    def forward(self, dfg_data: Data) -> torch.Tensor:
        h = self.gnn(dfg_data)
        return self.fc(h)
