from typing import List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.nn import (
    SAGEConv,
    TransformerConv,
    global_max_pool,
    global_mean_pool,
)


class _GraphTokenEncoder(nn.Module):
    def __init__(
        self,
        in_dim: int,
        edge_dim: int,
        hidden_dim: int,
        layers: int,
        kind: str,
    ) -> None:
        super().__init__()
        layers = max(1, layers)
        self.kind = kind
        self.edge_dim = edge_dim if edge_dim > 0 else None
        convs = []
        norms = []
        dims = [in_dim] + [hidden_dim] * layers
        for idx in range(layers):
            in_c = dims[idx]
            out_c = dims[idx + 1]
            if kind == "attn":
                conv = TransformerConv(
                    in_c,
                    out_c,
                    heads=2,
                    concat=False,
                    edge_dim=self.edge_dim,
                    dropout=0.1,
                )
            else:
                conv = SAGEConv(in_c, out_c)
            convs.append(conv)
            norms.append(nn.LayerNorm(out_c))
        self.convs = nn.ModuleList(convs)
        self.norms = nn.ModuleList(norms)
        self.hidden_dim = hidden_dim
        self.proj = nn.Linear(hidden_dim * 2, hidden_dim)

    def forward(self, data: Data) -> torch.Tensor:
        x = data.x
        edge_index = data.edge_index
        edge_attr = getattr(data, "edge_attr", None)
        if not isinstance(edge_attr, torch.Tensor) or edge_attr.numel() == 0:
            edge_attr = None
        # Type assertions for linter
        assert x is not None, "x cannot be None"
        assert edge_index is not None, "edge_index cannot be None"

        batch = getattr(data, "batch", None)
        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        for conv, norm in zip(self.convs, self.norms):
            h = x
            if self.kind == "attn":
                if edge_attr is not None:
                    x = conv(x, edge_index, edge_attr)
                else:
                    # Create dummy edge attributes for TransformerConv when edge_attr is None
                    num_edges = edge_index.size(1)
                    if self.edge_dim is not None:
                        dummy_edge_attr = torch.zeros(
                            (num_edges, self.edge_dim), dtype=x.dtype, device=x.device
                        )
                    else:
                        dummy_edge_attr = torch.zeros(
                            (num_edges, 1), dtype=x.dtype, device=x.device
                        )
                    x = conv(x, edge_index, dummy_edge_attr)
            else:
                x = conv(x, edge_index)
            x = norm(F.elu(x))
            if h is not None and x is not None and h.shape == x.shape:
                x = x + 0.1 * h
        if x is not None and batch is not None:
            pooled = torch.cat(
                [global_mean_pool(x, batch), global_max_pool(x, batch)], dim=-1
            )
        else:
            # Fallback if x or batch is None
            device = x.device if x is not None else torch.device("cpu")
            pooled = torch.zeros((1, self.hidden_dim * 2), device=device)
        return self.proj(pooled)


class DualStreamCrossGraphNet(nn.Module):
    def __init__(
        self,
        ast_in: int,
        ast_edge: int,
        dfg_in: int,
        dfg_edge: int,
        hid: int,
        out_classes: int,
        gnn_layers: int,
        fusion_depth: int,
        use_ast: bool,
        use_dfg: bool,
    ) -> None:
        super().__init__()
        self.use_ast = use_ast
        self.use_dfg = use_dfg
        self.hidden = hid
        streams = (1 if use_ast else 0) + (1 if use_dfg else 0)
        if streams == 0:
            streams = 1

        self.ast_encoder: Optional[_GraphTokenEncoder]
        if use_ast:
            self.ast_encoder = _GraphTokenEncoder(
                ast_in, ast_edge, hid, gnn_layers, kind="attn"
            )
        else:
            self.ast_encoder = None

        self.dfg_encoder: Optional[_GraphTokenEncoder]
        if use_dfg:
            self.dfg_encoder = _GraphTokenEncoder(
                dfg_in, dfg_edge, hid, max(1, gnn_layers - 1), kind="sage"
            )
        else:
            self.dfg_encoder = None

        if self.use_ast and self.use_dfg:
            fusion_in = hid * 4
        else:
            fusion_in = hid * 3
        heads = max(1, fusion_depth)
        fusion_layers = []
        in_dim = fusion_in
        for depth in range(heads - 1):
            fusion_layers.append(nn.Linear(in_dim, hid * 2))
            fusion_layers.append(nn.GELU())
            fusion_layers.append(nn.Dropout(0.2))
            in_dim = hid * 2
        fusion_layers.append(nn.Linear(in_dim, out_classes))
        self.classifier = nn.Sequential(*fusion_layers)
        if self.use_ast and self.use_dfg:
            self.gate = nn.Sequential(
                nn.LayerNorm(hid * 2),
                nn.Linear(hid * 2, hid),
                nn.GELU(),
                nn.Linear(hid, 2),
            )
        else:
            self.gate = None

    def forward(
        self,
        ast_data: Optional[Data] = None,
        dfg_data: Optional[Data] = None,
    ) -> torch.Tensor:
        # Allow SingleBranch-style calls by remapping single arguments to the active stream
        if (
            self.use_ast
            and not self.use_dfg
            and ast_data is None
            and dfg_data is not None
        ):
            ast_data, dfg_data = dfg_data, None
        if (
            self.use_dfg
            and not self.use_ast
            and dfg_data is None
            and ast_data is not None
        ):
            dfg_data, ast_data = ast_data, None

        device = next(self.classifier.parameters()).device
        reps: List[torch.Tensor] = []

        if self.use_ast and self.ast_encoder is not None:
            if ast_data is None:
                raise ValueError("AST data required for this model configuration")
            reps.append(self.ast_encoder(ast_data))
        if self.use_dfg and self.dfg_encoder is not None:
            if dfg_data is None:
                raise ValueError("DFG data required for this model configuration")
            reps.append(self.dfg_encoder(dfg_data))

        if not reps:
            reps = [torch.zeros((1, self.hidden), device=device)]

        combined = torch.cat(reps, dim=-1)
        if len(reps) > 1 and self.gate is not None:
            gate = torch.softmax(self.gate(combined), dim=-1)
            gated = torch.cat(
                [rep * gate[:, i].unsqueeze(-1) for i, rep in enumerate(reps)],
                dim=-1,
            )
        else:
            gated = torch.cat([reps[0], reps[0]], dim=-1)
        fused = torch.cat([combined, gated], dim=-1)
        return self.classifier(fused)
