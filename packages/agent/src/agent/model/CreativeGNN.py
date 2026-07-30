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
        # keep the same public contract: None disables edge features for TransformerConv
        self.edge_dim = edge_dim if edge_dim > 0 else None
        self._expected_edge_dim = int(edge_dim) if edge_dim > 0 else 0
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()

        if self.kind == "attn":
            # Use TransformerConv with optional edge attributes
            in_ch = in_dim
            for li in range(layers):
                out_ch = hidden_dim
                self.convs.append(
                    TransformerConv(
                        in_channels=in_ch,
                        out_channels=out_ch,
                        heads=1,
                        concat=False,
                        edge_dim=self.edge_dim,
                    )
                )
                self.norms.append(nn.LayerNorm(out_ch))
                in_ch = out_ch
        else:
            # Simple SAGE stack; no edge features
            in_ch = in_dim
            for li in range(layers):
                out_ch = hidden_dim
                self.convs.append(SAGEConv(in_ch, out_ch))
                self.norms.append(nn.LayerNorm(out_ch))
                in_ch = out_ch

        # After pooling (mean + max → 2 * hidden)
        self.proj = nn.Linear(hidden_dim * 2, hidden_dim)

    def _normalize_edge_attr(
        self,
        edge_attr: torch.Tensor | None,
        edge_index: torch.Tensor,
        x_like: torch.Tensor,
    ) -> torch.Tensor | None:
        """Make edge_attr match expected width for attention convs."""
        # If we don’t use edge attributes (self.edge_dim is None), return None.
        if self.edge_dim is None:
            return None

        E = int(edge_index.size(1)) if isinstance(edge_index, torch.Tensor) else 0
        want = max(1, self._expected_edge_dim)
        dtype = x_like.dtype
        device = x_like.device

        if not isinstance(edge_attr, torch.Tensor) or edge_attr.numel() == 0:
            return torch.zeros((E, want), dtype=dtype, device=device)

        if edge_attr.dim() == 1:
            edge_attr = edge_attr.view(-1, 1)

        edge_attr = edge_attr.to(dtype=dtype, device=device)

        # pad / truncate to match want
        c = edge_attr.size(1)
        if c < want:
            pad = torch.zeros((E, want - c), dtype=dtype, device=device)
            edge_attr = torch.cat([edge_attr, pad], dim=1)
        elif c > want:
            edge_attr = edge_attr[:, :want]

        # row count sanity
        if edge_attr.size(0) != E:
            if E == 0:
                edge_attr = torch.zeros((0, want), dtype=dtype, device=device)
            else:
                if edge_attr.size(0) > E:
                    edge_attr = edge_attr[:E]
                else:
                    times = (E + edge_attr.size(0) - 1) // edge_attr.size(0)
                    edge_attr = edge_attr.repeat(times, 1)[:E]
        return edge_attr

    def forward(self, data: Data) -> torch.Tensor:
        x = data.x
        edge_index = data.edge_index
        edge_attr = getattr(data, "edge_attr", None)

        assert x is not None, "x cannot be None"
        assert edge_index is not None, "edge_index cannot be None"

        batch = getattr(data, "batch", None)
        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        for conv, norm in zip(self.convs, self.norms):
            h = x
            if self.kind == "attn":
                edge_attr_norm = self._normalize_edge_attr(edge_attr, edge_index, x)
                if edge_attr_norm is None:
                    # (keeps your original fallback behavior)
                    num_edges = edge_index.size(1)
                    dummy_edge_attr = torch.zeros((num_edges, 1), dtype=x.dtype, device=x.device)
                    x = conv(x, edge_index, dummy_edge_attr)
                else:
                    x = conv(x, edge_index, edge_attr_norm)
            else:
                x = conv(x, edge_index)

            x = norm(F.elu(x))
            if h is not None and h.shape == x.shape:
                x = x + 0.1 * h

        pooled = torch.cat([global_mean_pool(x, batch), global_max_pool(x, batch)], dim=-1)
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
            self.ast_encoder = _GraphTokenEncoder(ast_in, ast_edge, hid, gnn_layers, kind="attn")
        else:
            self.ast_encoder = None

        self.dfg_encoder: Optional[_GraphTokenEncoder]
        if use_dfg:
            self.dfg_encoder = _GraphTokenEncoder(dfg_in, dfg_edge, hid, max(1, gnn_layers - 1), kind="sage")
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
        if self.use_ast and not self.use_dfg and ast_data is None and dfg_data is not None:
            ast_data, dfg_data = dfg_data, None
        if self.use_dfg and not self.use_ast and dfg_data is None and ast_data is not None:
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
            gate_logits = self.gate(combined)
            gate_weights = torch.softmax(gate_logits, dim=-1)
            gated = torch.cat(
                [rep * gate_weights[:, i].unsqueeze(-1) for i, rep in enumerate(reps)],
                dim=-1,
            )
        else:
            gated = torch.cat([reps[0], reps[0]], dim=-1)
        fused = torch.cat([combined, gated], dim=-1)
        logits = self.classifier(fused)
        return logits
