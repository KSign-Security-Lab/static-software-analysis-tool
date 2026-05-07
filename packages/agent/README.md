# Agent Module - GNN-Based Vulnerability Detection

## Table of Contents

1. [Overview](#overview)
2. [Execution Flow](#execution-flow)
3. [Component Responsibilities](#component-responsibilities)
4. [Data Transformations](#data-transformations)
5. [Model Architectures](#model-architectures)
6. [Configuration](#configuration)
7. [Integration with Analysis Pipeline](#integration-with-analysis-pipeline)

---

## Overview

The Agent module is a Graph Neural Network (GNN) based vulnerability detection system that learns to classify code functions as vulnerable or safe. It operates on graph representations of code (AST and DFG graphs) produced by the earlier stages of the static analysis pipeline, using PyTorch Geometric to build and train neural network models.

### The Problem Being Solved

Static analysis tools can identify potential vulnerabilities, but distinguishing true vulnerabilities from false positives requires understanding code semantics and context. Traditional rule-based approaches struggle with:

- **Context Sensitivity**: The same code pattern might be safe in one context but vulnerable in another
- **False Positives**: Many patterns flagged by static analysis are actually safe due to runtime checks or constraints
- **Pattern Complexity**: Vulnerabilities often involve complex interactions between multiple code elements

The Agent module addresses these challenges by learning from labeled examples. Given a dataset of code functions labeled as vulnerable or safe, it trains GNN models to recognize patterns that distinguish vulnerable code. The GNN architecture is particularly well-suited for this task because:

- **Graph Structure**: Code is naturally represented as graphs (AST for syntax, DFG for data flow), and GNNs excel at learning from graph-structured data
- **Feature Learning**: GNNs automatically learn relevant features from node and edge attributes, reducing the need for manual feature engineering
- **Multi-Modal Fusion**: The system can combine information from both AST and DFG graphs, capturing both syntactic and semantic patterns

### What the Module Does

The Agent module provides a complete machine learning pipeline:

1. **Data Loading**: Reads JSON files containing AST and DFG graph representations of code functions
2. **Graph Building**: Converts JSON graph data into PyTorch Geometric `Data` objects with node features, edge indices, and edge attributes
3. **Model Training**: Trains GNN models to classify functions as vulnerable (1) or safe (0) using labeled training data
4. **Model Evaluation**: Evaluates trained models on test data, computing accuracy, confusion matrices, and per-class statistics
5. **Configuration Management**: Saves complete training configurations for reproducibility and easy model loading

The module supports multiple model architectures (single-branch AST-only, single-branch DFG-only, late fusion, and dual-stream cross-graph) and provides flexible configuration options for hyperparameters, data paths, and training settings.

---

## Execution Flow

### Training Pipeline

When `train()` is called (via `uv run train`), the following sequence of operations occurs:

```python
def train(cfg: Optional[TrainConfig] = None, *, plot_max_points: Optional[int] = None) -> None:
    if cfg is None:
        cfg = _parse_train_args()  # Parse CLI arguments

    # 1. Setup
    torch.manual_seed(cfg.seed)
    device = torch.device(cfg.device)
    results_dir = cfg.save_name
    os.makedirs(results_dir, exist_ok=True)

    # 2. Load datasets from configured paths
    train_datasets_list = []
    test_datasets_list = []
    for data_entry in cfg.data_path:
        dataset_part = GenericJsonDataset(...)
        # Split into train/test
        train_datasets_list.append(...)
        test_datasets_list.append(...)

    # 3. Combine datasets and create dataloaders
    train_dataset = ConcatDataset(train_datasets_list)
    test_dataset = ConcatDataset(test_datasets_list)
    train_dataloader = build_dataloader(train_dataset, cfg, collate_fn=collate_multi)
    test_dataloader = build_dataloader(test_dataset, cfg, collate_fn=collate_multi)

    # 4. Infer model dimensions from data
    dims = infer_dims_from_dataset(train_dataset, kinds=["ast", "dfg"])
    ast_in, ast_edge_dim = dims["ast"]
    dfg_in, dfg_edge_dim = dims["dfg"]

    # 5. Create model based on mode
    model = select_model(cfg, ast_in, dfg_in, ast_edge_dim, dfg_edge_dim)
    model.to(device)

    # 6. Setup optimizer and loss function
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    class_weights = compute_class_weights(train_indices, train_dataset, cfg.out_classes)
    criterion = nn.CrossEntropyLoss(weight=class_weights.to(device))

    # 7. Train model
    train_model_from_dataset(cfg, train_dataloader, model, optimizer, criterion, device, ...)

    # 8. Save model and configuration
    torch.save(model.state_dict(), weights_path)
    save_training_config(cfg, results_dir, model_info)

    # 9. Evaluate on test set
    summary = evaluate_model(model, test_dataloader, device, cfg.mode, ...)
```

### Step 1: Configuration Parsing

The `_parse_train_args()` function parses command-line arguments and creates a `TrainConfig` object. CLI arguments override default values from the config class, allowing flexible configuration without code changes.

### Step 2: Dataset Loading

For each path in `cfg.data_path`, the system:

- Creates a `GenericJsonDataset` that reads JSON files from the path
- Uses `juliet_json_to_sample()` to convert each JSON file into a PyTorch Geometric `Data` object
- Splits the dataset into train and test sets based on `cfg.train_ratio`
- Applies label inference based on filename keywords (e.g., "bad" → 1, "patched" → 0)

### Step 3: DataLoader Creation

The combined datasets are wrapped in PyTorch `DataLoader` objects with:

- Custom `collate_multi` function that handles batching of graphs with multiple graph types (AST and DFG)
- Graph dimension harmonization to ensure all graphs in a batch have compatible feature dimensions
- Configurable batch size, number of workers, and shuffling

### Step 4: Dimension Inference

The system inspects sample data to determine:

- Node feature dimensions for AST and DFG graphs
- Edge attribute dimensions for AST and DFG graphs

These dimensions are needed to construct the model with the correct input sizes.

### Step 5: Model Selection

The `select_model()` function creates a model based on `cfg.mode`:

- `"ast"`: `ASTOnlyModel` - processes only AST graphs
- `"dfg"`: `DFGOnlyModel` - processes only DFG graphs
- `"late_fusion"`: `LateFusionModel` - processes AST and DFG separately, then concatenates representations
- `"both"`: `DualStreamCrossGraphNet` - processes AST and DFG with cross-graph attention

### Step 6: Training Setup

The training setup includes:

- Adam optimizer with configurable learning rate and weight decay
- Cross-entropy loss with class weights to handle imbalanced datasets
- Class weights computed from training data to balance the loss function

### Step 7: Training Loop

The `train_model_from_dataset()` function runs the training loop:

- For each epoch, iterates through batches
- Computes forward pass, loss, and backward pass
- Updates model parameters via optimizer
- Saves epoch checkpoints
- Tracks loss history for plotting

### Step 8: Model Persistence

After training, the system saves:

- Final model weights (`model.pt`)
- Training configuration (`training_config.json`) with all hyperparameters and model info
- Loss history (`loss.json`, `loss.csv`, `loss.png`)

### Step 9: Evaluation

The trained model is evaluated on the test set, producing:

- Accuracy metrics
- Confusion matrix (TP, TN, FP, FN)
- Per-class statistics
- Misclassified samples
- Evaluation summary saved to `evaluation.json`

### Evaluation Pipeline

When `evaluate()` is called (via `uv run evaluate`), the following sequence occurs:

```python
def evaluate() -> None:
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()
    results_dir = args.results_dir

    # 1. Load training configuration
    config = load_training_config(results_dir)
    cfg_dict = config["training_config"]
    cfg = TrainConfig(**cfg_dict)

    # 2. Reconstruct dataset using saved config
    train_dataset, test_dataset = ...  # Rebuild from cfg.data_path

    # 3. Load model checkpoint
    checkpoint_path = latest_epoch_checkpoint(results_dir) or os.path.join(results_dir, "model.pt")
    model = load_model_robust(checkpoint_path, device)
    mode = infer_mode_from_model(model)

    # 4. Create dataloader for evaluation split
    eval_dataset = test_dataset if args.split == "test" else train_dataset
    eval_dataloader = build_dataloader(eval_dataset, cfg, collate_fn=collate_multi)

    # 5. Run evaluation
    summary = evaluate_model(
        model=model,
        dataloader=eval_dataloader,
        device=device,
        mode=mode,
        max_samples=args.max_samples,
        output_dir=args.output_dir,
    )

    # 6. Save evaluation results
    summary_file = os.path.join(results_dir, "evaluation.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
```

### Step 1: Configuration Loading

The `load_training_config()` function reads `training_config.json` from the results directory and reconstructs the `TrainConfig` object. This ensures evaluation uses the same data paths, model architecture, and hyperparameters as training.

### Step 2: Dataset Reconstruction

The dataset is rebuilt from the saved configuration, ensuring the same train/test split and data preprocessing as during training.

### Step 3: Model Loading

The system loads the latest epoch checkpoint or the final model weights. The `load_model_robust()` function handles full model checkpoints (containing the complete model object) rather than just state dictionaries.

### Step 4: Evaluation Execution

The `evaluate_model()` function:

- Runs the model in evaluation mode (no gradient computation)
- Processes batches and collects predictions
- Computes accuracy, confusion matrix, and per-class statistics
- Optionally saves per-sample results with graph data for analysis

### Step 5: Results Persistence

Evaluation results are saved to `evaluation.json` in the results directory, providing a complete summary of model performance.

---

## Component Responsibilities

### GenericJsonDataset

**Primary Role**: Loads JSON files and converts them to PyTorch Geometric graph objects.

**Key Responsibility**: The dataset handles file I/O, JSON parsing, and graph construction. It supports flexible JSON schemas through Pydantic models and provides converters to transform JSON data into PyG `Data` objects.

**How It Works**:

The `GenericJsonDataset` class:

1. Recursively scans directory paths for JSON files
2. Loads and validates each JSON file using a Pydantic model class
3. Applies an optional pre-processing function (e.g., injecting file paths)
4. Converts each validated JSON object to a PyG `Data` object using a converter function
5. Caches converted samples for efficient repeated access

**Key Methods**:

- `__init__(paths, model_cls, converter, pre, strict, debug)`: Initializes the dataset with paths, model class for validation, converter function, and optional pre-processing
- `__getitem__(idx)`: Returns the converted PyG `Data` object for the sample at index `idx`
- `__len__()`: Returns the total number of samples

**Converter Functions**:

The `juliet_json_to_sample()` function is the primary converter used for vulnerability detection tasks. It:

- Extracts AST and DFG sections from JSON
- Builds PyG graphs from each section using `_build_graph_from_section()`
- Infers labels from filenames or explicit label fields
- Returns a `Data` object with `ast_graph`, `dfg_graph`, `y` (label), and metadata fields

### Graph Building Functions

**Primary Role**: Convert JSON graph representations into PyTorch Geometric `Data` objects.

**Key Responsibility**: The graph building functions handle the conversion from JSON structures (nodes, edges) to PyG tensors (node features, edge indices, edge attributes).

**How It Works**:

The `_build_graph_from_section()` function processes a JSON section containing nodes and edges:

1. **Node Feature Extraction**:
   - Extracts node lists from the JSON
   - For each node, flattens numeric features (preferring `node.feat` if present, otherwise flattening the entire node)
   - Creates a union of all feature keys across nodes
   - Builds a node feature matrix `x` where each row is a node and each column is a feature

2. **Edge Collection**:
   - Identifies edge families (keys starting with `edges_`, e.g., `edges_ast_pc`, `edges_ast_sb`, `edges_dfg`)
   - For each edge family, collects edges and builds one-hot family indicators
   - Extracts edge attributes (edge_type, guard_kind, guard_branch, etc.) and flattens them
   - Combines family one-hot vectors with attribute features

3. **Tensor Construction**:
   - Builds `edge_index` tensor in PyG format (2 x num_edges, with source and destination nodes)
   - Builds `edge_attr` tensor (num_edges x edge_feat_dim)
   - Stores feature names in `x_feature_names` and `edge_feature_names` attributes for dimension alignment

**Feature Harmonization**:

The `_harmonize_graph_dims()` function ensures graphs in a batch have compatible dimensions:

- Collects union of feature names across graphs
- Aligns node and edge features by name, padding missing features with zeros
- Enables batching of graphs with different feature sets

### Collate Function

**Primary Role**: Batches multiple graph samples into a single batch for efficient processing.

**Key Responsibility**: The `collate_multi()` function handles batching of samples that may contain multiple graph types (AST and DFG) and variable metadata fields.

**How It Works**:

```python
def collate_multi(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    # 1. Collect labels
    ys = [extract_label(item) for item in batch]
    out = {"y": torch.stack(ys)}

    # 2. Identify graph keys (keys ending with "_graph")
    graph_keys = [k for k in union_of_keys if k.endswith("_graph")]

    # 3. Batch each graph type
    for k in graph_keys:
        graphs = [item.get(k) or empty_graph() for item in batch]
        graphs = _harmonize_graph_dims(graphs)  # Align dimensions
        out[k] = Batch.from_data_list(graphs)  # PyG batching

    # 4. Pass through metadata as lists
    for meta_key in non_graph_keys:
        out[meta_key] = [item.get(meta_key) for item in batch]

    return out
```

The function:

1. Extracts and stacks labels from all samples
2. Identifies graph keys (typically `ast_graph` and `dfg_graph`)
3. Harmonizes graph dimensions to ensure compatibility
4. Uses PyG's `Batch.from_data_list()` to create batched graph objects
5. Passes through metadata fields (file names, function names, etc.) as lists

**Rationale**: PyTorch Geometric's `Batch` class efficiently handles graph batching by creating a single large graph with disconnected subgraphs. The batch object tracks which nodes belong to which original graph, enabling efficient parallel processing while maintaining graph structure.

### Model Selection

**Primary Role**: Creates the appropriate GNN model based on configuration.

**Key Responsibility**: The `select_model()` function instantiates the correct model architecture based on the `mode` configuration, with input dimensions inferred from the dataset.

**How It Works**:

```python
def select_model(
    cfg: TrainConfig,
    ast_in: int,
    dfg_in: int,
    edge_dim_ast: int,
    edge_dim_dfg: int,
) -> torch.nn.Module:
    if cfg.mode == "ast":
        return ASTOnlyModel(ast_in, ast_edge_dim, ...)
    if cfg.mode == "dfg":
        return DFGOnlyModel(dfg_in, dfg_edge_dim, ...)
    if cfg.mode == "late_fusion":
        return LateFusionModel(ast_in, ast_edge_dim, dfg_in, dfg_edge_dim, ...)
    if cfg.mode == "both":
        return DualStreamCrossGraphNet(ast_in, ast_edge, dfg_in, dfg_edge, ...)
```

Each model type has different input requirements:

- Single-branch models (`ast`, `dfg`) process one graph type
- Fusion models (`late_fusion`, `both`) process both AST and DFG graphs

**Rationale**: Different model architectures are suited for different scenarios. Single-branch models are simpler and faster, while fusion models can capture interactions between AST and DFG representations. The mode selection allows experimentation with different architectures.

### Training Loop

**Primary Role**: Executes the training process, updating model parameters to minimize loss.

**Key Responsibility**: The `train_model_from_dataset()` function orchestrates the training loop, handling forward passes, loss computation, backpropagation, and checkpointing.

**How It Works**:

```python
def train_model_from_dataset(
    cfg: TrainConfig,
    dataloader: TorchDataLoader,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    criterion: torch.nn.Module,
    device: torch.device,
    local_forward: ForwardFn,
    ...
):
    for epoch in range(cfg.epochs):
        model.train()
        for batch in dataloader:
            optimizer.zero_grad()

            labels = batch["y"].to(device)
            logits = local_forward(model, batch, device, cfg.mode)

            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            # Track loss
            iter_losses.append(loss.item())

        # Save epoch checkpoint
        torch.save(model, f"model_epoch_{epoch+1}.pt")
```

The training loop:

1. Sets model to training mode (enables dropout, batch norm updates)
2. Iterates through batches
3. Moves batch data to the specified device (CPU or GPU)
4. Computes forward pass using `local_forward()` which routes to the appropriate model forward method
5. Computes loss between predictions and true labels
6. Performs backpropagation to compute gradients
7. Updates model parameters via optimizer
8. Tracks loss history for monitoring and plotting
9. Saves checkpoint after each epoch

**Forward Function Routing**:

The `forward_by_mode()` function routes batches to the correct model forward method:

```python
def forward_by_mode(
    model: torch.nn.Module, batch: Dict[str, Any], device: torch.device, mode: str
) -> torch.Tensor:
    if mode == "ast":
        return model(batch["ast_graph"].to(device))
    if mode == "dfg":
        return model(batch["dfg_graph"].to(device))
    # both or late_fusion
    return model(batch["ast_graph"].to(device), batch["dfg_graph"].to(device))
```

This routing ensures that single-branch models receive only their required graph type, while fusion models receive both AST and DFG graphs.

### Evaluation Functions

**Primary Role**: Assesses model performance on test data.

**Key Responsibility**: The `evaluate_model()` function runs inference on a dataset and computes comprehensive performance metrics.

**How It Works**:

```python
def evaluate_model(
    model: torch.nn.Module,
    dataloader: TorchDataLoader,
    device: torch.device,
    mode: str,
    max_samples: int = 100,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    model.eval()
    sample_results = []

    with torch.no_grad():
        for batch in dataloader:
            for i in range(batch["y"].shape[0]):
                sample = extract_sample(batch, i)
                result = analyze_sample_with_model(model, sample, sample_id, device, mode)
                sample_results.append(result)

                if output_dir:
                    save_sample_results(result, output_dir, sample_id)

    # Compute summary statistics
    accuracy = correct_predictions / total_samples
    confusion = compute_confusion_matrix(sample_results)
    per_class_stats = compute_per_class_stats(sample_results)

    return {
        "evaluation_summary": {...},
        "confusion": confusion,
        "per_class_statistics": per_class_stats,
        "misclassified_samples": [...],
    }
```

The evaluation process:

1. Sets model to evaluation mode (disables dropout, uses batch norm statistics)
2. Disables gradient computation for efficiency
3. Processes batches and extracts individual samples
4. Runs inference on each sample using `analyze_sample_with_model()`
5. Collects predictions, confidences, and metadata
6. Optionally saves per-sample results with graph data for detailed analysis
7. Computes aggregate statistics (accuracy, confusion matrix, per-class metrics)
8. Returns comprehensive evaluation summary

**Sample Analysis**:

The `analyze_sample_with_model()` function processes a single sample:

```python
def analyze_sample_with_model(
    model: torch.nn.Module,
    sample: Dict[str, Any],
    sample_id: str,
    device: torch.device,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    # Wrap single sample in Batch
    ast_b = Batch.from_data_list([sample["ast_graph"]]) if sample.get("ast_graph") else None
    dfg_b = Batch.from_data_list([sample["dfg_graph"]]) if sample.get("dfg_graph") else None

    model.eval()
    with torch.no_grad():
        logits = model_forward(model, ast_b, dfg_b, mode)
        probs = torch.softmax(logits, dim=-1)
        predicted_label = int(torch.argmax(logits, dim=-1).item())
        confidence = float(probs[0, predicted_label].item())

    return {
        "sample_id": sample_id,
        "true_label": sample.get("y"),
        "predicted_label": predicted_label,
        "confidence": confidence,
        "correct_prediction": (true_label == predicted_label),
    }
```

This function handles single-sample inference, which is useful for detailed analysis and explanation generation.

---

## Data Transformations

### JSON → PyG Graph

The system transforms JSON graph representations into PyTorch Geometric `Data` objects through several stages:

**Input JSON Structure**:

```json
{
  "ast": {
    "nodes": [
      {"feat": {"node_type_id": 1, "in_loop": 0, "is_loop": 0, ...}},
      ...
    ],
    "edges_ast_pc": [[0, 1], [1, 2], ...],
    "edges_ast_sb": [[0, 3], ...],
    "edges_ast_guard": [
      {"src": 0, "dst": 1, "edge_type": 1, "guard_kind": 2, "guard_branch": 0}
    ]
  },
  "dfg": {
    "nodes": [...],
    "edges_dfg": [...]
  },
  "file": "vulnerable_function.c",
  "label": 1
}
```

**Transformation Process**:

1. **Node Feature Extraction**:
   - For each node, extracts the `feat` dictionary (or flattens the entire node if no `feat` key)
   - Collects all unique feature keys across all nodes
   - Creates a feature matrix where rows are nodes and columns are features
   - Missing features are filled with 0.0

2. **Edge Collection and Feature Building**:
   - Identifies edge families (keys starting with `edges_`)
   - For each edge family:
     - Collects edges (as [src, dst] pairs or {src, dst, ...} objects)
     - Creates one-hot family indicator (1.0 for the edge's family, 0.0 for others)
     - Extracts edge attributes (edge_type, guard_kind, etc.)
   - Combines family one-hot vectors with attribute features

3. **Tensor Construction**:
   - `x`: Node feature matrix (num_nodes x num_node_features)
   - `edge_index`: Edge connectivity (2 x num_edges, PyG format)
   - `edge_attr`: Edge feature matrix (num_edges x num_edge_features)

**Output PyG Data Object**:

```python
Data(
    x=tensor([[1.0, 0.0, 0.0, ...], ...]),  # Node features
    edge_index=tensor([[0, 1, 2, ...], [1, 2, 3, ...]]),  # Edge connectivity
    edge_attr=tensor([[1.0, 0.0, 0.0, 1.0, ...], ...]),  # Edge features
    x_feature_names=["node_type_id", "in_loop", "is_loop", ...],
    edge_feature_names=["fam_edges_ast_pc", "fam_edges_ast_sb", "edge_type", ...],
    y=tensor(1),  # Label
    file="vulnerable_function.c",
    function_name="vulnerable_func"
)
```

### Graph Batching

When multiple graphs are batched together:

1. **Dimension Harmonization**: Graphs with different feature sets are aligned by:
   - Computing union of feature names
   - Padding missing features with zeros
   - Ensuring consistent feature ordering

2. **PyG Batching**: PyTorch Geometric's `Batch.from_data_list()`:
   - Concatenates all node features into a single matrix
   - Concatenates all edge indices, offsetting node indices to prevent overlap
   - Creates a `batch` vector indicating which nodes belong to which graph
   - Concatenates edge attributes

3. **Result**: A single `Batch` object containing all graphs, with efficient parallel processing while maintaining graph boundaries.

---

## Model Architectures

### Single-Branch Models

**ASTOnlyModel** and **DFGOnlyModel** process a single graph type:

```python
class ASTOnlyModel(nn.Module):
    def __init__(self, ast_in, ast_edge_dim, hid, out_classes, gnn_layers):
        self.gnn = GINEStack(ast_in, ast_edge_dim, hid=hid, out_dim=hid, num_layers=gnn_layers)
        self.fc = nn.Linear(hid, out_classes)

    def forward(self, ast_data: Data) -> torch.Tensor:
        h = self.gnn(ast_data)  # Graph encoding
        return self.fc(h)  # Classification
```

**Architecture**:

- **GINEStack**: Stack of GINE (Graph Isomorphism Network with Edge features) convolutional layers
- Each layer applies graph convolution with edge features, followed by ReLU activation
- Final layer uses global mean pooling to aggregate node representations into a graph-level vector
- **Linear Classifier**: Single linear layer maps graph representation to class logits

**Rationale**: Single-branch models are simpler and faster, suitable when one graph type (AST or DFG) contains sufficient information for classification. They serve as baselines and can be more interpretable.

### Late Fusion Model

**LateFusionModel** processes AST and DFG separately, then concatenates representations:

```python
class LateFusionModel(nn.Module):
    def __init__(self, ast_in, ast_edge_dim, dfg_in, dfg_edge_dim, ...):
        self.ast_gnn = GINEStack(ast_in, ast_edge_dim, ...) if use_ast else None
        self.dfg_gnn = GINEStack(dfg_in, dfg_edge_dim, ...) if use_dfg else None
        self.fc = nn.Sequential(...)  # MLP for fusion

    def forward(self, ast_data: Data, dfg_data: Data):
        reps = []
        if self.ast_gnn:
            reps.append(self.ast_gnn(ast_data))
        if self.dfg_gnn:
            reps.append(self.dfg_gnn(dfg_data))
        h = torch.cat(reps, dim=-1)  # Concatenate representations
        return self.fc(h)  # Fusion and classification
```

**Architecture**:

- **Separate Encoders**: Independent GINE stacks for AST and DFG
- **Concatenation**: Graph representations are concatenated
- **Fusion MLP**: Multi-layer perceptron processes the concatenated representation

**Rationale**: Late fusion allows the model to learn separate representations for AST and DFG, then combine them. This is simpler than cross-graph attention but may miss interactions between the two graph types.

### Dual-Stream Cross-Graph Network

**DualStreamCrossGraphNet** uses attention mechanisms to enable cross-graph information flow:

```python
class DualStreamCrossGraphNet(nn.Module):
    def __init__(self, ast_in, ast_edge, dfg_in, dfg_edge, ...):
        self.ast_encoder = _GraphTokenEncoder(ast_in, ast_edge, hid, gnn_layers, kind="attn")
        self.dfg_encoder = _GraphTokenEncoder(dfg_in, dfg_edge, hid, gnn_layers-1, kind="sage")
        self.gate = nn.Sequential(...)  # Gating mechanism
        self.classifier = nn.Sequential(...)  # Final classifier

    def forward(self, ast_data: Data, dfg_data: Data):
        ast_repr = self.ast_encoder(ast_data)
        dfg_repr = self.dfg_encoder(dfg_data)

        # Cross-graph attention/gating
        combined = self.gate(torch.cat([ast_repr, dfg_repr], dim=-1))

        return self.classifier(combined)
```

**Architecture**:

- **AST Encoder**: Uses TransformerConv layers with attention mechanisms
- **DFG Encoder**: Uses SAGEConv layers (simpler, faster)
- **Gating Mechanism**: Learns to weight contributions from AST and DFG
- **Pooling**: Uses both global mean and max pooling, then projects to hidden dimension
- **Classifier**: Multi-layer MLP with GELU activations and dropout

**Rationale**: The dual-stream architecture enables the model to learn interactions between AST and DFG representations. The attention mechanism allows the model to focus on relevant parts of each graph type when making predictions. This is more expressive than late fusion but also more complex.

### Graph Encoder Details

**GINEStack** (used in single-branch and late fusion):

```python
class GINEStack(nn.Module):
    def __init__(self, in_dim, edge_dim, hid, out_dim, num_layers):
        self.convs = nn.ModuleList()
        for i in range(num_layers):
            mlp = nn.Sequential(nn.Linear(...), nn.ReLU(), nn.Linear(...))
            self.convs.append(GINEConv(mlp, edge_dim=edge_dim if edge_dim > 0 else None))

    def forward(self, data: Data):
        x, edge_index, edge_attr = data.x, data.edge_index, data.edge_attr
        for conv in self.convs:
            x = conv(x, edge_index, edge_attr)
            x = torch.relu(x)
        return global_mean_pool(x, data.batch)
```

**GraphTokenEncoder** (used in dual-stream):

```python
class _GraphTokenEncoder(nn.Module):
    def __init__(self, in_dim, edge_dim, hidden_dim, layers, kind):
        if kind == "attn":
            # TransformerConv with attention
            self.convs.append(TransformerConv(..., edge_dim=edge_dim))
        else:
            # SAGEConv (simpler)
            self.convs.append(SAGEConv(...))
        self.proj = nn.Linear(hidden_dim * 2, hidden_dim)  # After pooling

    def forward(self, data: Data):
        x = data.x
        for conv, norm in zip(self.convs, self.norms):
            x = conv(x, edge_index, edge_attr)
            x = norm(F.elu(x))
            x = x + 0.1 * residual  # Residual connection

        # Mean + Max pooling
        pooled = torch.cat([global_mean_pool(x, batch), global_max_pool(x, batch)], dim=-1)
        return self.proj(pooled)
```

**Key Differences**:

- **GINE**: Uses GINEConv with MLP edge processing, simpler architecture
- **TransformerConv**: Uses attention mechanism, more expressive but slower
- **Pooling**: GINE uses mean pooling only; GraphTokenEncoder uses mean + max pooling
- **Normalization**: GraphTokenEncoder uses LayerNorm; GINE uses ReLU only

---

## Configuration

### TrainConfig

The `TrainConfig` class (defined in `config.py`) provides comprehensive configuration for training:

```python
class TrainConfig(_BaseConfig):
    save_name: str = f"results/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    mode: Literal["both", "late_fusion", "ast", "dfg"] = "ast"
    data_path: List[DataPath] = [
        DataPath(path="data/train/...", label_key=LabelKey(keyword="bad", label=1)),
        ...
    ]
```

**Base Configuration** (`_BaseConfig`):

- `epochs`: Number of training epochs (default: 10)
- `lr`: Learning rate (default: 1e-3)
- `weight_decay`: L2 regularization (default: 1e-4)
- `device`: Device string like "cuda:0" or "cpu" (default: "cuda:1")
- `batch_size`: Batch size (default: 32)
- `num_workers`: DataLoader workers (default: 0)
- `pin_memory`: Pin memory for faster GPU transfer (default: False)
- `seed`: Random seed for reproducibility (default: 42)
- `hid`: Hidden dimension (default: 64)
- `gnn_layers`: Number of GNN layers (default: 3)
- `fusion_depth`: Depth of fusion MLP (default: 2)
- `shuffle`: Shuffle training data (default: True)
- `train_ratio`: Train/test split ratio (default: 0.9)
- `out_classes`: Number of output classes (default: 2)

**Data Path Configuration**:

Each `DataPath` entry specifies:

- `path`: Directory path containing JSON files
- `label_key`: Label inference rule
  - `keyword`: Filename keyword to match (e.g., "bad", "patched")
  - `label`: Label to assign when keyword is found (0 or 1)

**Label Inference Logic**:

1. Explicit label: If JSON has a `label` field, use it
2. Keyword matching: If filename contains the keyword, assign the specified label
3. Heuristic fallback: "patched"/"good"/"safe" → 0, "bad"/"vuln"/"unpatched" → 1
4. Default: 0 (safe)

**Configuration Persistence**:

Training saves the complete configuration to `training_config.json`:

```json
{
  "training_config": {
    "save_name": "results/exp1",
    "mode": "both",
    "epochs": 50,
    "lr": 0.001,
    ...
  },
  "model_info": {
    "model_type": "both",
    "model_class": "DualStreamCrossGraphNet",
    "ast_in": 16,
    "ast_edge_dim": 5,
    "dfg_in": 8,
    "dfg_edge_dim": 3
  },
  "training_metadata": {
    "timestamp": "2024-01-01T12:00:00",
    "results_dir": "results/exp1",
    "model_weights_path": "results/exp1/model.pt"
  }
}
```

This configuration file enables:

- Reproducible evaluation (same data paths, model architecture)
- Model loading without manual hyperparameter specification
- Experiment tracking and comparison

---

## Integration with Analysis Pipeline

The Agent module integrates with the broader static analysis pipeline:

### Data Flow

1. **CPG Generation**: Source code → CPG (via Joern)
2. **Template Generation**: CPG → Template nodes (normalized representation)
3. **AST/DFG Generation**: Template → AST/DFG graphs (Python extractors)
4. **JSON Export**: AST/DFG graphs → JSON files (CLI export)
5. **GNN Training/Evaluation**: JSON files → Trained model → Predictions

### CLI Integration

The Agent module is invoked independently via:

```bash
# Training
cd packages/agent
uv run train --save_name results/exp1 --device cuda:0 --epochs 50 --mode both

# Evaluation
uv run evaluate --results_dir results/exp1 --max_samples 200
```

The CLI entry points (`train` and `evaluate`) are defined in `pyproject.toml`:

```toml
[project.scripts]
train = "agent:train"
evaluate = "agent:evaluate"
```

These point to functions in `src/agent/__init__.py` that handle argument parsing and orchestrate the training/evaluation pipelines.

### Data Format Compatibility

The Agent module expects JSON files with the following structure (produced by the CLI's `full` mode):

```json
{
  "file": "function_name",
  "label": 1,
  "ast_result": {
    "nodes": [...],
    "edges_ast_pc": [...],
    "edges_ast_sb": [...],
    "edges_ast_guard": [...]
  },
  "dfg_result": {
    "nodes": [...],
    "edges_dfg": [...]
  }
}
```

The `juliet_json_to_sample()` converter handles variations in JSON structure, supporting:

- Direct `ast`/`dfg` keys
- Nested `ast_result`/`dfg_result` keys
- Various edge family naming conventions
- Flexible node feature structures

### Model Deployment

Trained models can be used for:

1. **Batch Prediction**: Process directories of code functions and classify them
2. **Integration with Static Analysis**: Use model predictions to filter or prioritize static analysis findings
3. **Continuous Learning**: Retrain models with new labeled data as it becomes available

The saved model checkpoints (`model.pt` or `model_epoch_*.pt`) can be loaded programmatically:

```python
from agent.evaluate import load_model_robust, infer_mode_from_model
import torch

device = torch.device("cuda:0")
model = load_model_robust("results/exp1/model_epoch_10.pt", device)
mode = infer_mode_from_model(model)

# Use model for inference
model.eval()
with torch.no_grad():
    logits = model(ast_batch, dfg_batch)  # or model(ast_batch) for single-branch
    predictions = torch.softmax(logits, dim=-1).argmax(dim=-1)
```

---

## Conclusion

The Agent module provides a complete GNN-based vulnerability detection system, from data loading through model training to evaluation. Its modular design supports multiple model architectures, flexible data formats, and comprehensive configuration management. By learning from labeled examples, it complements rule-based static analysis tools with learned pattern recognition capabilities.
