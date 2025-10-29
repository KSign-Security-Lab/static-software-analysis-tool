from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type

import torch
from pydantic import BaseModel
from pydantic import ConfigDict
from torch.utils.data import Dataset
from torch_geometric.data import Data


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _empty_graph() -> Data:
    return Data(
        x=torch.zeros((1, 0), dtype=torch.float),
        edge_index=torch.zeros((2, 0), dtype=torch.long),
        edge_attr=torch.zeros((0, 1), dtype=torch.float),
    )


def _infer_label_from_path(path: str) -> int:
    """Heuristic label from file path.

    Vulnerable (1) if path contains any of: 'bad', 'vuln', 'unpatched', 'unsafe'.
    Safe (0) if path contains any of: 'good', 'patched', 'safe', 'fixed'.
    Default 0 when unsure.
    """
    try:
        s = path.lower()
        if any(k in s for k in ["patched", "good", "safe", "fixed"]):
            return 0
        if any(k in s for k in ["bad", "vuln", "unpatched", "unsafe"]):
            return 1
        return 0
    except Exception:
        return 0


def _flatten_numeric(
    obj: Any, prefix: str = "", out: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """
    Recursively flatten dictionaries/lists/objects into {key: float}, keeping numeric leaves only.
    Keys are dot/idx-joined for stability.
    """
    if out is None:
        out = {}
    key_prefix = (prefix + ".") if prefix else ""

    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten_numeric(v, key_prefix + str(k), out)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _flatten_numeric(v, key_prefix + str(i), out)
    else:
        if isinstance(obj, (int, float, bool)):
            out[prefix] = float(obj)
    return out


def _union_sorted_keys(dicts: Iterable[Dict[str, float]]) -> List[str]:
    keys = set()
    for d in dicts:
        keys.update(d.keys())
    return sorted(keys)


def _build_x_from_nodes(nodes: List[Any]) -> Tuple[torch.Tensor, List[str]]:
    """
    Accepts list of nodes (dicts or NodeModel).
    If node has 'feat' dict, flatten it; else flatten entire node.
    """
    flats: List[Dict[str, float]] = []
    for n in nodes:
        if isinstance(n, BaseModel):
            n = n.model_dump()
        elif hasattr(n, "dict") and callable(getattr(n, "dict")):
            n = n.dict()
        if isinstance(n, dict) and isinstance(n.get("feat"), dict):
            flats.append(_flatten_numeric(n["feat"]))
        else:
            flats.append(_flatten_numeric(n))
    cols = _union_sorted_keys(flats)
    if not cols:
        return torch.zeros((max(1, len(nodes)), 0), dtype=torch.float), []
    rows = [[_to_float(f.get(k, 0.0)) for k in cols] for f in flats]
    return torch.tensor(rows, dtype=torch.float), cols


def _normalize_edge_item(e: Any) -> Tuple[int, int, float]:
    """
    Normalize a single edge into (src, dst, attr_float).
    Supports [src,dst], [src,dst,attr], or {src,dst,attr}.
    """
    if isinstance(e, (list, tuple)) and len(e) >= 2:
        src = _to_int(e[0])
        dst = _to_int(e[1])
        attr = _to_float(e[2]) if len(e) > 2 else 0.0
        return src, dst, attr
    if isinstance(e, dict):
        src = _to_int(e.get("src", 0))
        dst = _to_int(e.get("dst", 0))
        attr = _to_float(e.get("attr", 0.0))
        return src, dst, attr
    return 0, 0, 0.0


def _collect_config(model_obj: BaseModel) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Reads node/edge keys from model_config.
    - node_keys: List[str]
    - edge_keys: either List[str] (family==field name) OR Dict[str, str|List[str]]
      Returns (node_keys, edge_map) where edge_map: family_name -> List[field_names]
    """
    cfg = getattr(model_obj, "model_config", {}) or {}
    node_keys = list(cfg.get("node_keys", ["nodes"]))
    raw_edges = cfg.get("edge_keys", ["edges"])

    edge_map: Dict[str, List[str]] = {}
    if isinstance(raw_edges, dict):
        for fam, fields in raw_edges.items():
            if isinstance(fields, str):
                edge_map[fam] = [fields]
            elif isinstance(fields, list):
                edge_map[fam] = [str(f) for f in fields]
    elif isinstance(raw_edges, list):
        # family name is the field name itself
        for f in raw_edges:
            edge_map[str(f)] = [str(f)]
    else:
        # fallback
        edge_map["edges"] = ["edges"]

    # dedupe while preserving order
    seen = set()
    node_keys = [k for k in node_keys if not (k in seen or seen.add(k))]
    # ensure deterministic order of families
    edge_map = {
        fam: fields for fam, fields in sorted(edge_map.items(), key=lambda kv: kv[0])
    }
    return node_keys, edge_map


# ──────────────────────────────────────────────────────────────────────────────
# Juliet-style JSON → Sample(Data with nested graphs)
# ──────────────────────────────────────────────────────────────────────────────


class AnyGraphModel(BaseModel):
    """Permissive model to accept arbitrary JSON structures.

    We only use `.model_dump()` to access the raw JSON payload.
    """

    model_config = ConfigDict(extra="allow")


def _build_graph_from_section(
    section: Dict[str, Any], *, edge_family_prefixes: Optional[List[str]] = None
) -> Data:
    """Build a PyG Data from a JSON section with 'nodes' and edge lists.

    - Nodes: expect list of dicts with a 'feat' dict → flatten numeric features
    - Edges: if multiple families are present (e.g., edges_ast_pc, edges_ast_sb, ...),
      create one-hot family indicators plus optional scalar 'value' when triples include it.
      If a single family with rich attributes is present (e.g., DFG's edges_dfg with 'feat'),
      flatten that attribute dict to edge features.
    """
    nodes = section.get("nodes", []) if isinstance(section, dict) else []

    # Build node feature matrix
    node_feats: List[Dict[str, float]] = []
    for n in nodes:
        if isinstance(n, dict) and isinstance(n.get("feat"), dict):
            node_feats.append(_flatten_numeric(n["feat"]))
        else:
            node_feats.append(_flatten_numeric(n))
    x_cols = _union_sorted_keys(node_feats)
    if x_cols:
        x = torch.tensor(
            [[_to_float(f.get(k, 0.0)) for k in x_cols] for f in node_feats],
            dtype=torch.float,
        )
    else:
        x = torch.zeros((max(1, len(nodes)), 0), dtype=torch.float)

    # Collect edge families if present. Support mixed families: some rich (dict attrs), some simple.
    edges: List[List[int]] = []
    per_edge_feat_dicts: List[Dict[str, float]] = []

    # Determine families: any key starting with 'edges_'
    if edge_family_prefixes is None:
        edge_family_prefixes = [
            k
            for k in (section.keys() if isinstance(section, dict) else [])
            if str(k).startswith("edges_")
        ]
    fams = sorted(edge_family_prefixes)

    # Build features: one-hot family flags + flattened attributes (edge_type/value/guard fields, etc.)
    fam_col_names = [f"fam_{fam}" for fam in fams]
    attr_keys_seen: set[str] = set()

    temp_rows: List[Tuple[List[int], Dict[str, float]]] = []
    for fam_idx, fam in enumerate(fams):
        raw = section.get(fam, [])
        # Normalize singleton objects into list
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        for e in raw:
            src = dst = 0
            feat: Dict[str, float] = {}
            # family one-hot
            feat[fam_col_names[fam_idx]] = 1.0

            if isinstance(e, (list, tuple)):
                if len(e) >= 2:
                    src = _to_int(e[0])
                    dst = _to_int(e[1])
                if len(e) >= 3:
                    # third field could be dict or scalar. If scalar treat as edge_type for AST triples.
                    if isinstance(e[2], dict):
                        flat = _flatten_numeric(e[2].get("feat", e[2]))
                        for k, v in flat.items():
                            feat[str(k)] = float(v)
                    else:
                        feat["edge_type"] = _to_float(e[2])
            elif isinstance(e, dict):
                src = _to_int(e.get("src", 0))
                dst = _to_int(e.get("dst", 0))
                # flatten known fields; prefer explicit edge_type/guard_kind/guard_branch
                if "edge_type" in e:
                    feat["edge_type"] = _to_float(e.get("edge_type", 0))
                if "guard_kind" in e:
                    feat["guard_kind"] = _to_float(e.get("guard_kind", 0))
                if "guard_branch" in e:
                    feat["guard_branch"] = _to_float(e.get("guard_branch", 0))
                # flatten nested attr/feat if provided
                attr_obj = e.get("attr") or e.get("feat")
                if isinstance(attr_obj, dict):
                    flat = _flatten_numeric(attr_obj)
                    for k, v in flat.items():
                        # avoid clobbering already set keys
                        if k not in ("src", "dst") and k not in feat:
                            feat[str(k)] = float(v)

            # track attribute keys
            for k in feat.keys():
                if k not in fam_col_names:
                    attr_keys_seen.add(k)
            temp_rows.append(([src, dst], feat))

    # Lay out features with consistent columns
    attr_cols = sorted(attr_keys_seen - set(fam_col_names))
    edge_feat_names = fam_col_names + attr_cols

    for srcdst, feat in temp_rows:
        edges.append(srcdst)
        row: List[float] = []
        # fam cols
        for name in fam_col_names:
            row.append(float(feat.get(name, 0.0)))
        # attr cols
        for name in attr_cols:
            row.append(float(feat.get(name, 0.0)))
        per_edge_feat_dicts.append(
            {name: val for name, val in zip(edge_feat_names, row)}
        )

    # Build tensors
    edge_attr_rows: List[List[float]] = [
        [feat.get(n, 0.0) for n in edge_feat_names] for feat in per_edge_feat_dicts
    ]

    if edges:
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
        edge_attr = (
            torch.tensor(edge_attr_rows, dtype=torch.float)
            if edge_attr_rows
            else torch.zeros((len(edges), 1), dtype=torch.float)
        )
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
        edge_attr = torch.zeros((0, max(len(edge_feat_names), 1)), dtype=torch.float)
        if not edge_feat_names:
            edge_feat_names = ["edge_attr"]

    g = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
    g.x_feature_names = x_cols
    g.edge_feature_names = edge_feat_names
    return g


def _infer_label_from_json(
    raw: Dict[str, Any],
    fallback_path: Optional[str] = None,
    label_keys: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Infer label from JSON payload using common fields and name hints.

    Priority:
      1) Explicit fields: 'label', 'is_vulnerable', 'vulnerable', 'target'
      2) Keyword hints in function/file/template names
      3) Fallback to path-based heuristic
    Returns 0 for safe, 1 for vulnerable.
    """
    # 1) Explicit fields
    label = raw.get("label")
    if label is not None:
        try:
            if isinstance(label, bool):
                return 1 if label else 0
            # strings like "1", "0", "bad", "good"
            if isinstance(label, str):
                v = label.strip().lower()
                if v in {"bad", "vuln", "vulnerable", "unpatched", "unsafe"}:
                    return 1
                if v in {"good", "patched", "safe", "fixed"}:
                    return 0
                return 1 if int(v) != 0 else 0
            return 1 if int(label) != 0 else 0
        except Exception:
            pass
    for k in ("is_vulnerable", "vulnerable", "target"):
        if k in raw:
            try:
                v = raw[k]
                if isinstance(v, bool):
                    return 1 if v else 0
                if isinstance(v, (int, float)):
                    return 1 if int(v) != 0 else 0
                if isinstance(v, str):
                    t = v.strip().lower()
                    if t in {"true", "1", "yes", "bad", "vuln", "vulnerable", "unpatched", "unsafe"}:
                        return 1
                    if t in {"false", "0", "no", "good", "patched", "safe", "fixed"}:
                        return 0
            except Exception:
                pass

    # 2) Configured label keyword rules (use filename, not function)
    file_name = raw.get("file") or raw.get("filename") or raw.get("source_template")
    fname_lower = str(file_name or "").lower()
    if fallback_path:
        try:
            import os as _os
            fname_lower = _os.path.basename(fallback_path).lower()
        except Exception:
            pass
    if label_keys:
        try:
            if len(label_keys) == 1:
                lk = label_keys[0]
                kw = str(lk.get("keyword", "")).lower()
                lbl = int(lk.get("label", 0))
                if kw and kw in fname_lower:
                    return 1 if lbl != 0 else 0
                else:
                    # Invert label when keyword not present
                    return 0 if lbl != 0 else 1
            # Multiple rules: first match wins; otherwise fall through
            for lk in label_keys:
                kw = str(lk.get("keyword", "")).lower()
                if kw and kw in fname_lower:
                    lbl = int(lk.get("label", 0))
                    return 1 if lbl != 0 else 0
        except Exception:
            pass
    # Built-in hints consider filename and function name
    func_name = raw.get("function_name") or raw.get("function")
    key_str = " ".join(str(s) for s in [fname_lower, func_name] if s).lower()
    if any(k in key_str for k in ["patched", "good", "safe", "fixed"]):
        return 0
    if any(k in key_str for k in ["bad", "vuln", "vulnerable", "unpatched", "unsafe"]):
        return 1

    # 3) Fallback to file path if provided
    if fallback_path:
        return _infer_label_from_path(fallback_path)
    return 0


def juliet_json_to_sample(
    model_obj: BaseModel,
    *,
    label_keys: Optional[List[Dict[str, Any]]] = None,
) -> Data:
    """Converter: take raw Juliet-like JSON and build a sample Data stub
    with attributes:
      - y: label tensor (0: good, 1: bad)
      - ast_graph: Data
      - dfg_graph: Data (if available)
      - function_name, path, file
    """
    raw = model_obj.model_dump()

    ast_section = raw.get("ast", {}) if isinstance(raw, dict) else {}
    dfg_section = raw.get("dfg", {}) if isinstance(raw, dict) else {}

    ast_graph = _build_graph_from_section(
        ast_section,
        edge_family_prefixes=[
            k for k in ast_section.keys() if str(k).startswith("edges_")
        ],
    )
    dfg_graph = None
    if isinstance(dfg_section, dict) and dfg_section:
        dfg_graph = _build_graph_from_section(
            dfg_section, edge_family_prefixes=["edges_dfg"]
        )  # dfg-specific

    # Derive label robustly from JSON content and names
    file_name = raw.get("file") or raw.get("filename") or raw.get("source_template")
    func_name = raw.get("function_name") or raw.get("function")
    # Use injected on-disk path for filename-based rules
    fallback_path = raw.get("__file_path")
    y = _infer_label_from_json(raw, fallback_path=fallback_path, label_keys=label_keys)

    sample = Data()
    sample.y = torch.tensor(y, dtype=torch.long)
    sample.ast_graph = ast_graph
    if dfg_graph is not None:
        sample.dfg_graph = dfg_graph
    if file_name:
        sample.file = file_name
    if func_name:
        sample.function_name = func_name
    return sample


# ──────────────────────────────────────────────────────────────────────────────
# Default converter that obeys model_config["node_keys"]/["edge_keys"]
# ──────────────────────────────────────────────────────────────────────────────


def config_pydantic_to_pyg(instance: BaseModel) -> Data:
    """
    Conversion logic:
      1) If 'x' + 'edge_index' exist → use directly (edge_attr optional).
      2) Else, read node/edge collections from model_config keys and build:
         - Nodes: merge all node collections; flatten numeric features (preferring node.feat).
         - Edges: merge all configured families with one-hot family channels.
           If any edge has nonzero attr, append a scalar 'value' column.
    """
    dump = instance.model_dump()

    # Fast path: direct tensors
    if "x" in dump and "edge_index" in dump:
        x = torch.tensor(dump["x"], dtype=torch.float)
        edge_index = torch.tensor(dump["edge_index"], dtype=torch.long)
        ea = dump.get("edge_attr")
        if ea is None:
            ea = torch.zeros(
                (edge_index.shape[1] if edge_index.numel() else 0, 1), dtype=torch.float
            )
        else:
            ea = torch.tensor(ea, dtype=torch.float)
            if ea.ndim == 1:
                ea = ea.view(-1, 1)
        data = Data(x=x, edge_index=edge_index, edge_attr=ea)
        for k, v in dump.items():
            if k not in {"x", "edge_index", "edge_attr"}:
                setattr(data, k, v)
        return data

    # Config-driven path
    node_keys, edge_map = _collect_config(instance)

    # Nodes: merge all configured node lists
    node_acc: List[Any] = []
    for k in node_keys:
        v = dump.get(k, [])
        if isinstance(v, list):
            node_acc.extend(v)
    x, x_cols = _build_x_from_nodes(node_acc)

    # Edges: collect per-family (family name from config)
    fam_names: List[str] = []
    edges_by_family: List[List[Tuple[int, int, float]]] = []

    for fam, fields in edge_map.items():
        fam_edges: List[Tuple[int, int, float]] = []
        for fkey in fields:
            raw = dump.get(fkey, [])
            if isinstance(raw, list):
                for e in raw:
                    fam_edges.append(_normalize_edge_item(e))
        fam_names.append(fam)
        edges_by_family.append(fam_edges)

    F = len(fam_names)
    all_edges: List[List[int]] = []
    onehots: List[List[float]] = []
    scalars: List[float] = []
    any_scalar = False

    for fam_idx, fam_edges in enumerate(edges_by_family):
        for src, dst, val in fam_edges:
            all_edges.append([src, dst])
            oh = [0.0] * F
            if F > 0:
                oh[fam_idx] = 1.0
            onehots.append(oh)
            scalars.append(float(val))
            if val != 0.0:
                any_scalar = True

    if all_edges:
        edge_index = torch.tensor(all_edges, dtype=torch.long).t().contiguous()
        if F == 0:
            edge_attr = torch.zeros((len(all_edges), 1), dtype=torch.float)
            edge_feat_names = ["edge_attr"]
        else:
            oh = torch.tensor(onehots, dtype=torch.float)
            if any_scalar:
                val = torch.tensor(scalars, dtype=torch.float).view(-1, 1)
                edge_attr = torch.cat([oh, val], dim=1)  # [E, F+1]
                edge_feat_names = fam_names + ["value"]
            else:
                edge_attr = oh  # [E, F]
                edge_feat_names = fam_names
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
        edge_attr = torch.zeros((0, max(F, 1)), dtype=torch.float)
        edge_feat_names = fam_names if F > 0 else ["edge_attr"]

    data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
    data.x_feature_names = x_cols
    data.edge_feature_names = edge_feat_names

    # Attach undeclared fields as attributes for convenience
    declared = set(node_keys)
    for fam_fields in edge_map.values():
        declared.update(fam_fields)
    for k, v in dump.items():
        if k not in declared:
            setattr(data, k, v)

    return data


# ──────────────────────────────────────────────────────────────────────────────
# Dataset
# ──────────────────────────────────────────────────────────────────────────────


class GenericJsonDataset(Dataset):
    """
    Generic JSON → Pydantic (user model REQUIRED) → PyG Data (config-driven).

    Args:
      paths:     File or directory; recurses for *.json
      model_cls: Required Pydantic model class (BaseGraphModel or subclass)
      converter: Optional converter (defaults to config_pydantic_to_pyg)
      pre:       Optional pre(json_obj, path)->json_obj
      post:      Optional post(Data, model_obj, path)->Data
      strict:    If True, invalid files are skipped; else they become empty graphs
      debug:     Print summary
    """

    def __init__(
        self,
        paths: str,
        model_cls: Type[BaseModel],
        *,
        converter: Optional[Callable[[BaseModel], Data]] = None,
        pre: Optional[Callable[[Dict[str, Any], str], Dict[str, Any]]] = None,
        post: Optional[Callable[[Data, BaseModel, str], Data]] = None,
        strict: bool = False,
        debug: bool = False,
    ):
        self.model_cls = model_cls
        self.converter = converter or config_pydantic_to_pyg
        self.pre = pre
        self.post = post
        self.strict = strict
        self.debug = debug

        self.files = self._collect(paths)
        if not self.files:
            raise FileNotFoundError(f"No JSON files under: {paths}")

        self.items: List[Data] = []
        kept = skipped = 0

        for fp in self.files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if self.pre:
                    raw = self.pre(raw, fp)

                model_obj = self.model_cls.model_validate(raw)
                data = self.converter(model_obj)
                data.path = fp

                if self.post:
                    data = self.post(data, model_obj, fp)

                self.items.append(data)
                kept += 1
            except Exception:
                # Invalid or unreadable JSON: keep a placeholder sample with
                # consistent structure so downstream collate never breaks.
                if self.strict:
                    skipped += 1
                    continue
                placeholder = Data()
                placeholder.y = torch.tensor(
                    _infer_label_from_path(fp), dtype=torch.long
                )
                placeholder.ast_graph = _empty_graph()
                # Some datasets may not have DFG; keep attribute for consistency
                placeholder.dfg_graph = _empty_graph()
                placeholder.path = fp
                self.items.append(placeholder)
                kept += 1

        if self.debug:
            print(
                f"GenericJsonDataset → kept: {kept}, skipped: {skipped}, total: {kept + skipped}"
            )

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> Data:
        return self.items[idx]

    @staticmethod
    def _collect(paths: str) -> List[str]:
        if os.path.isfile(paths):
            return [paths] if paths.endswith(".json") else []
        out: List[str] = []
        for root, _, files in os.walk(paths):
            for fn in files:
                if fn.endswith(".json"):
                    out.append(os.path.join(root, fn))
        return out
