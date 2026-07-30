from pydantic import BaseModel
from datetime import datetime
from typing import List, Literal, Tuple


class ASTNodeFeatSchema(BaseModel):
    node_type_id: int
    train_mask: int
    in_loop: int
    is_loop: int
    ctx_guard_strength: int
    ctx_upper_bound_norm: int
    is_buffer_decl: int
    buffer_size_state: int


class ASTNodeSchema(BaseModel):
    feat: ASTNodeFeatSchema


class ASTGuardEdgeSchema(BaseModel):
    src: int
    dst: int
    edge_type: int
    guard_kind: int
    guard_branch: int


class ASTSchema(BaseModel):
    nodes: ASTNodeSchema
    edges_ast_pc: List[Tuple[int, int, int]]
    edges_ast_sb: List[Tuple[int, int, int]]
    edges_ast_guard: ASTGuardEdgeSchema


class Schema(BaseModel):
    ast: ASTSchema


class _BaseConfig(BaseModel):
    epochs: int = 10
    lr: float = 1e-3
    weight_decay: float = 1e-4
    device: str = "cuda:1"
    batch_size: int = 32
    num_workers: int = 0
    pin_memory: bool = False
    seed: int = 42
    hid: int = 64
    gnn_layers: int = 3
    fusion_depth: int = 2
    shuffle: bool = True
    train_ratio: float = 0.9
    out_classes: int = 2
    strict_schema: bool = True
    infer_dims: bool = True


class LabelKey(BaseModel):
    keyword: str
    label: int


class DataPath(BaseModel):
    path: str
    # Single label rule per datapath (required)
    label_key: LabelKey


class TrainConfig(_BaseConfig):
    save_name: str = f"results/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    mode: Literal["both", "late_fusion", "ast", "dfg"] = "ast"

    # data_path is explicitly a list of DataPath entries
    data_path: List[DataPath] = [
        DataPath(
            path="data/train/CWE121_Stack_Based_Buffer_Overflow",
            label_key=LabelKey(
                keyword="bad",
                label=1,
            ),
        ),
        DataPath(
            path="data/train/CWE122_Heap_Based_Buffer_Overflow",
            label_key=LabelKey(
                keyword="bad",
                label=1,
            ),
        ),
        DataPath(
            path="data/test",
            label_key=LabelKey(
                keyword="patched",
                label=0,
            ),
        ),
    ]
