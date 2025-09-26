import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import torch
from torch.utils.data import Dataset
from torch_geometric.data import Data


def keep_original_value(value: Any) -> Any:
    return value


DEFAULT_FEATURE_CONVERTERS: Dict[str, Dict[str, Any]] = {
    "ast_result": {
        "node": {
            "feat": {
                "node_type_id": keep_original_value,
                "train_mask": keep_original_value,
                "in_loop": keep_original_value,
                "is_loop": keep_original_value,
                "ctx_guard_strength": keep_original_value,
                "ctx_upper_bound_norm": keep_original_value,
                "is_buffer_decl": keep_original_value,
                "buffer_size_state": keep_original_value,
                "buffer_size_norm": keep_original_value,
                "call_sem_cat_id": keep_original_value,
                "call_flag_danger_unbounded": keep_original_value,
                "call_flag_len_linked_to_dst": keep_original_value,
                "call_flag_sizeof_non_dst": keep_original_value,
                "call_flag_has_varargs": keep_original_value,
                "call_dst_is_field": keep_original_value,
                "call_size_kind": keep_original_value,
                "call_len_linked_to_dst_extended": keep_original_value,
                "call_size_is_sizeof_base_struct": keep_original_value,
                "call_size_mismatch_field": keep_original_value,
                "alloc_sizeof_state": keep_original_value,
            },
        },
        "edges_ast_pc": [keep_original_value, keep_original_value, keep_original_value],
        "edges_ast_sb": [keep_original_value, keep_original_value, keep_original_value],
        "edges_ast_guard": {
            "src": keep_original_value,
            "dst": keep_original_value,
            "edge_type": keep_original_value,
            "guard_kind": keep_original_value,
            "guard_branch": keep_original_value,
        },
    },
    "dfg_result": {
        "node": {
            "feat": {
                "in_degree_dfg": keep_original_value,
                "out_degree_dfg": keep_original_value,
                "def_count": keep_original_value,
                "use_count": keep_original_value,
                "is_buffer_access": keep_original_value,
                "is_sink_assign": keep_original_value,
                "is_sink_call_unbounded": keep_original_value,
                "is_sink_call_bounded": keep_original_value,
                "call_dst_indexed": keep_original_value,
                "call_len_linked_to_dst": keep_original_value,
                "call_size_nonconst": keep_original_value,
                "call_danger_unbounded": keep_original_value,
            },
        },
        "edges_dfg": [
            keep_original_value,
            keep_original_value,
            {
                "feat": {
                    "flow_id": keep_original_value,
                    "guard_kind": keep_original_value,
                    "has_lower_guard": keep_original_value,
                    "has_upper_guard": keep_original_value,
                    "upper_guard_norm": keep_original_value,
                }
            },
        ],
    },
}


class JsonDataset(Dataset):
    """Load JSON/JSONL data and expose it as a PyTorch Dataset.

    - Accepts a file path or a directory. If a directory is given, recursively
      finds files ending with .json or .jsonl.
    - Items are standard dicts; when available, `ast_result` and `dfg_result`
      are converted into PyTorch Geometric `Data` using shared builders to match
      the training/evaluation pipeline.
    - Optional `transform` is applied to each item after construction.
    """

    def __init__(
        self,
        paths: List[str],
        labels: Optional[Dict[str, bool]] = None,
        transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        limit: Optional[int] = None,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.files: List[str] = []
        self.transform = transform
        self.dataset: List[Dict[str, Any]] = []
        for path in self.paths:
            self.files.extend(self._collect_files(path))
        self.debug = debug

        if not self.files:
            raise FileNotFoundError(f"No JSON/JSONL files found under: {self.paths}")
        # stats
        kept = 0
        skipped = 0

        # Initialize labels after files are known
        self.labels = labels or self._default_labels()

        for file_path in self.files:
            json_data = json.load(open(file_path, "r", encoding="utf-8"))
            json_data["label"] = self.labels.get(file_path, False)
            json_data["path"] = file_path
            if self._check_converter_matches_json(json_data):
                self._convert_to_pyg(json_data)
                # Coerce label to torch.long
                try:
                    json_data["label"] = torch.tensor(
                        int(bool(json_data["label"])), dtype=torch.long
                    )
                except Exception:
                    json_data["label"] = torch.tensor(0, dtype=torch.long)
                self.dataset.append(json_data)
                kept += 1
            else:
                skipped += 1

            if limit is not None and len(self.dataset) >= limit:
                break

        # simple stats
        self.load_stats = {"kept": kept, "skipped": skipped}
        total = kept + skipped
        if self.debug:
            print(
                f"JsonDataset stats → kept: {kept}, skipped: {skipped}, total: {total}"
            )
        if total > 0 and (skipped / total) >= 0.10:
            raise ValueError(
                f"Too many samples skipped during load: {skipped}/{total} (>=10%)."
            )

    def _default_labels(self) -> Dict[str, bool]:
        labels = {}
        for file in self.files:
            # If file has "bad" then it is a vulnerable function
            labels[file] = file.split("/")[-1].lower().find("bad") != -1
        return labels

    def _collect_files(self, path: str) -> List[str]:
        if os.path.isfile(path):
            return [path]
        files: List[str] = []
        for root, _, filenames in os.walk(path):
            for name in filenames:
                if name.endswith(".json") or name.endswith(".jsonl"):
                    files.append(os.path.join(root, name))
        files.sort()
        return files

    def _check_converter_matches_json(self, json_data: Dict[str, Any]) -> bool:
        # Accept if at least one converter kind matches its schema (strictly checks all declared keys)
        has_any = False
        for kind, schema_any in DEFAULT_FEATURE_CONVERTERS.items():
            if not (
                isinstance(schema_any, dict)
                and isinstance(schema_any.get("node"), dict)
            ):
                continue
            sub = json_data.get(kind)
            if not isinstance(sub, dict):
                continue

            node_feat_keys = list(schema_any["node"].get("feat", {}).keys())
            # Collect all expected non-node keys from schema (edges, edges_*, etc.)
            expected_edge_keys = [k for k in schema_any.keys() if k != "node"]

            nodes = sub.get("nodes")
            if not isinstance(nodes, list) or not nodes:
                continue

            ok_nodes = True
            for node in nodes:
                if not isinstance(node, dict):
                    ok_nodes = False
                    break
                feats = node.get("feat")
                if not isinstance(feats, dict):
                    ok_nodes = False
                    break
                for k in node_feat_keys:
                    if k not in feats:
                        ok_nodes = False
                        break
                if not ok_nodes:
                    break

            if not ok_nodes:
                continue

            # Strict: all expected edge keys must exist and be list/tuple
            edges_ok = True
            for edge_key in expected_edge_keys:
                val = sub.get(edge_key)
                if not isinstance(val, (list, tuple)):
                    edges_ok = False
                    break
            if not edges_ok:
                continue

            has_any = True

        return has_any

    def _convert_to_pyg(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        for kind, schema in DEFAULT_FEATURE_CONVERTERS.items():
            sub = json_data.get(kind)
            if not isinstance(sub, dict):
                continue

            # Build node features flat matrix using schema's node.feat order
            node_spec = schema.get("node", {}).get("feat", {})
            node_keys: List[str] = list(node_spec.keys())
            nodes = sub.get("nodes")
            if not isinstance(nodes, list) or not nodes:
                continue

            feats: List[List[float]] = []
            for node in nodes:
                feat_dict = node.get("feat", {}) if isinstance(node, dict) else {}
                row: List[float] = []
                for k in node_keys:
                    fn = node_spec.get(k, keep_original_value)
                    val = feat_dict.get(k, 0)
                    try:
                        val = fn(val)
                    except Exception:
                        pass
                    try:
                        row.append(float(val))
                    except Exception:
                        row.append(0.0)
                feats.append(row)
            x = torch.tensor(feats, dtype=torch.float)

            # Build edges by concatenating arrays for all edge keys declared by schema
            edge_arrays: List[torch.Tensor] = []
            for edge_key in [k for k in schema.keys() if k != "node"]:
                v = sub.get(edge_key)
                if isinstance(v, (list, tuple)) and len(v) > 0:
                    try:
                        # Handle complex edge structures (like DFG with nested dicts)
                        if kind == "dfg_result" and edge_key == "edges_dfg":
                            # Extract src, dst, and edge features from DFG structure
                            edge_data = []
                            for edge in v:
                                if isinstance(edge, list) and len(edge) >= 3:
                                    src, dst = edge[0], edge[1]
                                    edge_feat = (
                                        edge[2] if isinstance(edge[2], dict) else {}
                                    )
                                    feat_dict = edge_feat.get("feat", {})
                                    # Extract flow_id as primary edge feature
                                    flow_id = feat_dict.get("flow_id", 0)
                                    edge_data.append([src, dst, flow_id])
                            if edge_data:
                                arr = torch.tensor(edge_data)
                                if arr.ndim == 1:
                                    arr = arr.unsqueeze(0)
                                edge_arrays.append(arr)
                        elif kind == "ast_result" and edge_key == "edges_ast_guard":
                            # Handle AST guard edges with complex structure
                            edge_data = []
                            for edge in v:
                                if isinstance(edge, dict):
                                    src = edge.get("src", 0)
                                    dst = edge.get("dst", 0)
                                    edge_type = edge.get("edge_type", 0)
                                    guard_kind = edge.get("guard_kind", 0)
                                    # Combine edge_type and guard_kind as edge features
                                    edge_feature = edge_type * 10 + guard_kind
                                    edge_data.append([src, dst, edge_feature])
                            if edge_data:
                                arr = torch.tensor(edge_data)
                                if arr.ndim == 1:
                                    arr = arr.unsqueeze(0)
                                edge_arrays.append(arr)
                        else:
                            # Standard processing for other edge types
                            arr = torch.tensor(v)
                            if arr.ndim == 1:
                                arr = arr.unsqueeze(0)
                            edge_arrays.append(arr)
                    except Exception as e:
                        print(f"Warning: Failed to process {edge_key} edges: {e}")
                        pass

            if edge_arrays:
                edges_array = torch.vstack(edge_arrays)
                edge_index = edges_array[:, :2].to(torch.long).t().contiguous()
                if edges_array.size(1) >= 3:
                    edge_attr = (
                        edges_array[:, 2].to(torch.long).view(-1, 1).to(torch.float)
                    )
                else:
                    edge_attr = torch.zeros((edge_index.size(1), 1), dtype=torch.float)
            else:
                edge_index = torch.zeros((2, 0), dtype=torch.long)
                edge_attr = torch.zeros((0, 1), dtype=torch.float)

            data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
            data.x_feature_names = node_keys
            data.edge_feature_names = ["edge_type_id"]
            # Map to expected keys for training compatibility
            if kind == "ast_result":
                json_data["ast_graph"] = data
            elif kind == "dfg_result":
                json_data["dfg_graph"] = data
            json_data[f"{kind}_graph"] = data

            # Preserve original node and edge information for human-friendly output
            json_data[f"{kind}_original_nodes"] = nodes
            json_data[f"{kind}_original_edges"] = []
            for edge_key in [k for k in schema.keys() if k != "node"]:
                v = sub.get(edge_key)
                if isinstance(v, (list, tuple)) and len(v) > 0:
                    json_data[f"{kind}_original_edges"].extend(v)

        return json_data

    def __len__(self) -> int:
        return len(self.dataset)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        item = dict(self.dataset[idx])
        if self.transform is not None:
            item = self.transform(item)
        return item
