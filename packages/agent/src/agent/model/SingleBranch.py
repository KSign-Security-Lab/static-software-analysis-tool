import torch
import torch.nn as nn
from torch_geometric.data import Data
from torch_geometric.nn import GINEConv, global_mean_pool


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
        self.edge_dim = int(edge_dim)

        self.convs = nn.ModuleList()

        def make_mlp(in_f, out_f):
            return nn.Sequential(nn.Linear(in_f, hid), nn.ReLU(), nn.Linear(hid, out_f))

        self.convs.append(
            GINEConv(make_mlp(in_dim, hid), edge_dim=self.edge_dim)
            if self.edge_dim > 0
            else GINEConv(make_mlp(in_dim, hid))
        )
        for _ in range(max(0, num_layers - 2)):
            self.convs.append(
                GINEConv(make_mlp(hid, hid), edge_dim=self.edge_dim)
                if self.edge_dim > 0
                else GINEConv(make_mlp(hid, hid))
            )
        self.convs.append(
            GINEConv(make_mlp(hid, out_dim), edge_dim=self.edge_dim)
            if self.edge_dim > 0
            else GINEConv(make_mlp(hid, out_dim))
        )

    def _normalize_edge_attr(
        self,
        edge_attr: torch.Tensor | None,
        edge_index: torch.Tensor,
        x_like: torch.Tensor,
    ) -> torch.Tensor | None:
        """Ensure edge_attr matches self.edge_dim; pad/truncate or synthesize zeros."""
        if self.edge_dim <= 0:
            return None  # model was built without edge features

        E = int(edge_index.size(1)) if isinstance(edge_index, torch.Tensor) else 0
        dtype = x_like.dtype
        device = x_like.device

        # synthesize when missing/empty
        if not isinstance(edge_attr, torch.Tensor) or edge_attr.numel() == 0:
            return torch.zeros((E, self.edge_dim), dtype=dtype, device=device)

        # ensure 2D
        if edge_attr.dim() == 1:
            edge_attr = edge_attr.view(-1, 1)

        # dtype/device match
        edge_attr = edge_attr.to(dtype=dtype, device=device)

        # pad/truncate to expected width
        c = edge_attr.size(1)
        if c < self.edge_dim:
            pad = torch.zeros((E, self.edge_dim - c), dtype=dtype, device=device)
            edge_attr = torch.cat([edge_attr, pad], dim=1)
        elif c > self.edge_dim:
            edge_attr = edge_attr[:, : self.edge_dim]

        # ensure correct number of rows (in case of malformed inputs)
        if edge_attr.size(0) != E:
            if E == 0:
                edge_attr = torch.zeros((0, self.edge_dim), dtype=dtype, device=device)
            else:
                # best-effort: crop or tile to match E
                if edge_attr.size(0) > E:
                    edge_attr = edge_attr[:E]
                else:
                    times = (E + edge_attr.size(0) - 1) // edge_attr.size(0)
                    edge_attr = edge_attr.repeat(times, 1)[:E]
        return edge_attr

    def forward(self, data: Data) -> torch.Tensor:
        x, edge_index = data.x, data.edge_index
        edge_attr = getattr(data, "edge_attr", None)
        edge_attr = self._normalize_edge_attr(edge_attr, edge_index, x)

        for i, conv in enumerate(self.convs):
            if self.edge_dim > 0:
                x = conv(x, edge_index, edge_attr)
            else:
                x = conv(x, edge_index)
            if i < len(self.convs) - 1:
                x = torch.relu(x)

        # pool per graph
        batch_vec = getattr(data, "batch", None)
        if isinstance(batch_vec, torch.Tensor) and batch_vec.numel() == x.size(0):
            return global_mean_pool(x, batch_vec)
        return global_mean_pool(
            x, torch.zeros(x.size(0), dtype=torch.long, device=x.device)
        )


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
