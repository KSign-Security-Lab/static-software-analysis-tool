import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple, Union

import torch
from torch.utils.data import Dataset

from .ASTGraph import AST
from .DFGGraph import DFG

Kind = Literal["ast", "dfg"]


@dataclass(frozen=True)
class Sample:
    path: str
    kind: Kind


# Keys exposed by dataset items and batches (metadata for loaders)
DATASET_META_KEYS: Tuple[str, ...] = ("graph", "label", "path", "kind", "function")

# Feature keys included in the training dataset for AST/DFG graphs
# These reflect the TypedDicts in ASTGraph.py and DFGGraph.py
# Per-entity feature keys
AST_NODE_FEATURE_KEYS: Tuple[str, ...] = (
    "node_type_id",
    "train_mask",
    "in_loop",
    "is_loop",
    "ctx_guard_strength",
    "ctx_upper_bound_norm",
    "is_buffer_decl",
    "buffer_size_state",
    "buffer_size_norm",
    "call_sem_cat_id",
    "call_flag_danger_unbounded",
    "call_flag_len_linked_to_dst",
    "call_flag_sizeof_non_dst",
    "call_flag_has_varargs",
    "call_dst_is_field",
    "call_size_kind",
    "call_len_linked_to_dst_extended",
    "call_size_is_sizeof_base_struct",
    "call_size_mismatch_field",
    "alloc_sizeof_state",
)

# AST edges
AST_EDGE_PC_KEYS: Tuple[str, ...] = ("src", "dst", "edge_type")
AST_EDGE_SB_KEYS: Tuple[str, ...] = ("src", "dst", "edge_type")
AST_EDGE_GUARD_KEYS: Tuple[str, ...] = (
    "src",
    "dst",
    "edge_type",
    "guard_kind",
    "guard_branch",
)

DFG_NODE_FEATURE_KEYS: Tuple[str, ...] = (
    "nodeType",
    "inDegreeDFG",
    "outDegreeDFG",
    "defCount",
    "useCount",
    "isBufferAccess",
    "isSinkAssignment",
    "isSinkCallUnbounded",
    "isSinkCallBounded",
    "callDestinationIndexed",
    "callLengthLinkedToDestination",
    "callSizeNonConstant",
    "callDangerUnbounded",
)

DFG_EDGE_FEATURE_KEYS: Tuple[str, ...] = (
    "flow",
    "guard",
    "hasLowerGuard",
    "hasUpperGuard",
    "upperGuardNormalization",
)

# Combined feature-key registry by entity
FEATURE_KEYS: Dict[str, Tuple[str, ...]] = {
    "ASTNode": AST_NODE_FEATURE_KEYS,
    "ASTEdgePC": AST_EDGE_PC_KEYS,
    "ASTEdgeSB": AST_EDGE_SB_KEYS,
    "ASTEdgeGuard": AST_EDGE_GUARD_KEYS,
    "DFGNode": DFG_NODE_FEATURE_KEYS,
    "DFGEdge": DFG_EDGE_FEATURE_KEYS,
}


def _is_ast_wrapped(obj: Any) -> bool:
    return isinstance(obj, dict) and "ast_result" in obj


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _iter_files(root: str, suffixes: Tuple[str, ...]) -> Iterable[str]:
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.endswith(suffixes):
                yield os.path.join(dirpath, name)


class GraphDataset(Dataset):
    """PyTorch Dataset for AST/DFG graphs stored as JSON.

    - kind="ast": returns a dictionary with key "graph" holding AST (List[ASTGraph])
      normalized to the unwrapped array form (AST = List[ASTGraph]). Handles both
      wrapped shape { ast_result: {..} } and direct array shape [{..}].
    - kind="dfg": returns a dictionary with key "graph" holding DFG (List[DFGGraph]).

    Each item also includes: "label" (Optional[int]), "path" (str), "kind" (Literal).
    """

    def __init__(
        self,
        data_dir: Union[str, os.PathLike],
        *,
        kind: Kind,
        file_suffix: Optional[Tuple[str, ...]] = None,
        preload: bool = False,
    ) -> None:
        super().__init__()
        self.data_dir = str(data_dir)
        self.kind: Kind = kind
        if file_suffix is None:
            if kind == "ast":
                file_suffix = ("_astTree.json", "_templateTree_astTree.json")
            else:
                file_suffix = ("_dfg.json",)
        self.file_suffix = file_suffix

        self.samples: List[Sample] = []
        for path in _iter_files(self.data_dir, self.file_suffix):
            self.samples.append(Sample(path=path, kind=self.kind))

        # Optional preload into memory
        self._cache: Dict[int, Dict[str, Any]] = {}
        if preload:
            for i in range(len(self.samples)):
                self._cache[i] = self._load_item(i)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        if idx < 0 or idx >= len(self.samples):
            raise IndexError("index out of range")
        if idx in self._cache:
            return self._cache[idx]
        return self._load_item(idx)

    def _load_item(self, idx: int) -> Dict[str, Any]:
        s = self.samples[idx]
        obj = _load_json(s.path)

        if s.kind == "ast":
            # Normalize to AST (List[ASTGraph])
            graph: AST
            if _is_ast_wrapped(obj):
                # Convert { ast_result: {...} } into [{...}]
                graph = [obj["ast_result"]]
            elif isinstance(obj, list):
                graph = obj  # already AST = List[ASTGraph]
            else:
                raise ValueError(f"Unsupported AST JSON structure in {s.path}")

            # Filter features to defined keys
            self._filter_ast_features(graph)

            function_name = self._extract_function_name_from_ast(graph, s.path)
            label = self._label_from_function(function_name)

            item: Dict[str, Any] = {
                "graph": graph,
                "label": label,
                "path": s.path,
                "kind": s.kind,
                "function": function_name,
            }
            return item

        # DFG
        if not isinstance(obj, list):
            raise ValueError(f"Unsupported DFG JSON structure in {s.path}")
        dfg: DFG = obj

        # Filter features to defined keys
        self._filter_dfg_features(dfg)

        function_name = self._extract_function_name_from_dfg(dfg, s.path)
        label = self._label_from_function(function_name)

        item = {
            "graph": dfg,
            "label": label,
            "path": s.path,
            "kind": s.kind,
            "function": function_name,
        }
        return item

    # -------------------------------
    # Static helpers (single module)
    # -------------------------------
    @staticmethod
    def _label_from_function(function_name: str) -> int:
        """Return 1 if function name contains 'bad' (case-insensitive), else 0."""
        return 1 if "bad" in function_name.lower() else 0

    @staticmethod
    def _fallback_function_name_from_path(path: str) -> str:
        stem = os.path.splitext(os.path.basename(path))[0]
        return stem

    @staticmethod
    def _extract_function_name_from_ast(graph: AST, path: str) -> str:
        """Try to read a function name from AST content; fallback to file name.
        We look for a FunctionEntry node's 'code' if present; otherwise fallback.
        """
        try:
            if isinstance(graph, list) and graph:
                g0 = graph[0]
                # nodes are dicts with keys: sid, node_type, code, orig_id, feat, ...
                for n in g0.get("nodes", []):
                    if n.get("node_type") == "FunctionEntry":
                        code = n.get("code") or ""
                        # heuristic: function signature like 'void foo(...)'
                        name = GraphDataset._parse_name_from_code(code)
                        if name:
                            return name
        except Exception:
            pass
        return GraphDataset._fallback_function_name_from_path(path)

    @staticmethod
    def _extract_function_name_from_dfg(graph: DFG, path: str) -> str:
        """Try to read a function name from DFG content; fallback to file name.
        We look for a node with debug.label == 'METHOD' and parse debug.code.
        """
        try:
            if isinstance(graph, list) and graph:
                g0 = graph[0]
                for n in g0.get("nodes", []):
                    dbg = n.get("debug", {})
                    if isinstance(dbg, dict) and dbg.get("label") == "METHOD":
                        code = dbg.get("code") or ""
                        name = GraphDataset._parse_name_from_code(code)
                        if name:
                            return name
        except Exception:
            pass
        return GraphDataset._fallback_function_name_from_path(path)

    @staticmethod
    def _parse_name_from_code(code: str) -> str:
        """Extract function name token from code like 'int foo(bar)' -> 'foo'."""
        try:
            if not code:
                return ""
            # strip leading/trailing spaces and qualifiers
            s = code.strip()
            # find name before first '(' and after last space
            if "(" in s:
                before = s.split("(", 1)[0].strip()
                # function name may follow spaces or *
                tokens = [t for t in before.replace("*", " ").split() if t]
                if tokens:
                    return tokens[-1]
        except Exception:
            return ""
        return ""

    # -------------------------------
    # Feature filtering (projection)
    # -------------------------------
    @staticmethod
    def _filter_ast_features(graph: AST) -> None:
        try:
            for g in graph:
                # Nodes: keep only declared node feature keys
                nodes = g.get("nodes", [])
                for n in nodes:
                    feat = n.get("feat")
                    if isinstance(feat, dict):
                        # prune in-place: remove keys not in allowlist
                        for k in list(feat.keys()):
                            if k not in AST_NODE_FEATURE_KEYS:
                                feat.pop(k, None)
                # Edges_pc and edges_sb are tuples; nothing to filter
                # Guard edges are dicts; keep only declared guard keys
                guards = g.get("edges_ast_guard", [])
                for e in guards:
                    if isinstance(e, dict):
                        for k in list(e.keys()):
                            if k not in AST_EDGE_GUARD_KEYS:
                                e.pop(k, None)
        except Exception:
            # Fail-soft: do not crash dataset on unexpected shapes
            pass

    @staticmethod
    def _filter_dfg_features(graph: DFG) -> None:
        try:
            for g in graph:
                # Nodes: features dict
                nodes = g.get("nodes", [])
                for n in nodes:
                    feats = n.get("features")
                    if isinstance(feats, dict):
                        for k in list(feats.keys()):
                            if k not in DFG_NODE_FEATURE_KEYS:
                                feats.pop(k, None)
                # Edges: features dict
                edges = g.get("edges", [])
                for e in edges:
                    feats = e.get("features")
                    if isinstance(feats, dict):
                        for k in list(feats.keys()):
                            if k not in DFG_EDGE_FEATURE_KEYS:
                                feats.pop(k, None)
        except Exception:
            # Fail-soft
            pass


def default_collate_fn(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A permissive collate function that keeps variable-sized graphs as-is.

    Returns a dict with lists for each field. You can replace this with a graph
    library-specific collate (e.g., PyG/DGL) later.
    """
    out: Dict[str, Any] = {
        "graph": [b["graph"] for b in batch],
        "label": torch.tensor([int(b["label"]) for b in batch], dtype=torch.long),
        "path": [b["path"] for b in batch],
        "kind": [b["kind"] for b in batch],
        "function": [b.get("function", "") for b in batch],
    }
    return out


# -------------------------------
# Paired AST/DFG dataset (by common filename prefix)
# -------------------------------


def _basename_prefix(path: str) -> str:
    base = os.path.basename(path)
    name, _ext = os.path.splitext(base)
    for suf in ("_templateTree_astTree", "_astTree", "_dfg"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


class PairedGraphDataset(Dataset):
    """Pairs AST and DFG files by common filename prefix across two directories.

    - Drops files without a matching counterpart.
    - Normalizes AST structure (wrapped/unwrapped) to AST = List[ASTGraph].
    - Filters features to declared keys.
    """

    def __init__(
        self,
        ast_dir: Union[str, os.PathLike],
        dfg_dir: Union[str, os.PathLike],
        preload: bool = False,
    ) -> None:
        super().__init__()
        self.ast_dir = str(ast_dir)
        self.dfg_dir = str(dfg_dir)

        ast_files = list(
            _iter_files(self.ast_dir, ("_astTree.json", "_templateTree_astTree.json"))
        )
        dfg_files = list(_iter_files(self.dfg_dir, ("_dfg.json",)))
        ast_map: Dict[str, str] = {_basename_prefix(p): p for p in ast_files}
        dfg_map: Dict[str, str] = {_basename_prefix(p): p for p in dfg_files}

        common = sorted(set(ast_map.keys()) & set(dfg_map.keys()))
        self.samples: List[Tuple[str, str]] = [(ast_map[k], dfg_map[k]) for k in common]

        self._cache: Dict[int, Dict[str, Any]] = {}
        if preload:
            for i in range(len(self.samples)):
                self._cache[i] = self._load_item(i)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        if idx in self._cache:
            return self._cache[idx]
        return self._load_item(idx)

    def _load_item(self, idx: int) -> Dict[str, Any]:
        ast_path, dfg_path = self.samples[idx]
        ast_obj = _load_json(ast_path)
        dfg_obj = _load_json(dfg_path)

        # Normalize AST
        if _is_ast_wrapped(ast_obj):
            ast_graph: AST = [ast_obj["ast_result"]]
        elif isinstance(ast_obj, list):
            ast_graph = ast_obj
        else:
            raise ValueError(f"Unsupported AST JSON structure: {ast_path}")

        if not isinstance(dfg_obj, list):
            raise ValueError(f"Unsupported DFG JSON structure: {dfg_path}")
        dfg_graph: DFG = dfg_obj

        # Feature filtering
        GraphDataset._filter_ast_features(ast_graph)
        GraphDataset._filter_dfg_features(dfg_graph)

        # Label from function name (AST)
        func = GraphDataset._extract_function_name_from_ast(ast_graph, ast_path)
        label = GraphDataset._label_from_function(func)

        return {
            "ast_graph": ast_graph,
            "dfg_graph": dfg_graph,
            "label": label,
            "function": func,
            "ast_path": ast_path,
            "dfg_path": dfg_path,
        }


def paired_collate_fn(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "ast_graph": [b["ast_graph"] for b in batch],
        "dfg_graph": [b["dfg_graph"] for b in batch],
        "label": torch.tensor([int(b["label"]) for b in batch], dtype=torch.long),
        "function": [b.get("function", "") for b in batch],
        "ast_path": [b["ast_path"] for b in batch],
        "dfg_path": [b["dfg_path"] for b in batch],
    }
