from typing import Optional

import torch
import torch.nn as nn
from torch_geometric.data import Data  # pyright: ignore[reportMissingImports]
from torch_geometric.nn import (  # pyright: ignore[reportMissingImports]
    GINEConv,
    global_mean_pool,
)


class GINEStack(nn.Module):
    def __init__(
        self,
        in_dim: int,
        edge_dim: int = 0,
        hid: int = 64,
        out_dim: int = 64,
        num_layers: int = 3,
    ):
        super().__init__()
        assert num_layers >= 2, "num_layers must be at least 2"
        self.edge_dim = edge_dim

        self.convs = nn.ModuleList()

        # First layer: in_dim -> hid
        mlp_first = nn.Sequential(
            nn.Linear(in_dim, hid), nn.ReLU(), nn.Linear(hid, hid)
        )
        self.convs.append(
            GINEConv(mlp_first, edge_dim=edge_dim)
            if edge_dim > 0
            else GINEConv(mlp_first)
        )

        # Middle layers: hid -> hid
        for _ in range(max(0, num_layers - 2)):
            mlp_mid = nn.Sequential(nn.Linear(hid, hid), nn.ReLU(), nn.Linear(hid, hid))
            self.convs.append(
                GINEConv(mlp_mid, edge_dim=edge_dim)
                if edge_dim > 0
                else GINEConv(mlp_mid)
            )

        # Final layer: hid -> out_dim
        mlp_last = nn.Sequential(
            nn.Linear(hid, hid), nn.ReLU(), nn.Linear(hid, out_dim)
        )
        self.convs.append(
            GINEConv(mlp_last, edge_dim=edge_dim)
            if edge_dim > 0
            else GINEConv(mlp_last)
        )

    def forward(self, data: Data) -> torch.Tensor:
        x, edge_index = data.x, data.edge_index
        edge_attr = getattr(data, "edge_attr", None)
        # Resolve dtype/device safely for type checker
        x_dtype: torch.dtype = x.dtype if isinstance(x, torch.Tensor) else torch.float32
        x_device = x.device if isinstance(x, torch.Tensor) else None
        # Always provide a float edge_attr of shape (E, edge_dim)
        if not isinstance(edge_attr, torch.Tensor) or edge_attr.numel() == 0:
            num_edges = (
                edge_index.size(1) if isinstance(edge_index, torch.Tensor) else 0
            )
            edge_attr = torch.zeros(
                (num_edges, max(1, self.edge_dim)), dtype=x_dtype, device=x_device
            )
        else:
            # ensure dtype matches x
            edge_attr = edge_attr.to(dtype=x_dtype)

        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index, edge_attr)
            # ReLU after every layer except the last one (keep representation flexible)
            if i < len(self.convs) - 1:
                x = torch.relu(x)
        batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)
        return global_mean_pool(x, batch)
