"""
Model evaluation module.

This module provides comprehensive model evaluation with explanations and filename tracking.
"""

import json
import os
from collections import defaultdict
from typing import Any, Dict, Optional, Union

import numpy as np
import torch

from .explain import analyze_decision_rationale, save_decision_rationale


def load_training_config(results_dir: str) -> Dict[str, Any]:
    """Load training configuration saved by train.py.

    Expects a file named `training_config.json` in the results directory.
    Returns the parsed configuration dictionary.
    """
    config_path = os.path.join(results_dir, "training_config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"training_config.json not found in {results_dir}")

    with open(config_path, "r") as f:
        config: Dict[str, Any] = json.load(f)

    return config


def create_model_from_config(
    config: Dict[str, Any], device: torch.device
) -> torch.nn.Module:
    """Create model and load weights based on saved training configuration.

    Args:
        config: The configuration dictionary loaded from training_config.json
        device: Target torch.device

    Returns:
        torch.nn.Module ready for evaluation
    """
    training_cfg = config.get("training_config", {})

    mode = training_cfg.get("mode", "both")
    hid = int(training_cfg.get("hid", 64))
    gnn_layers = int(training_cfg.get("gnn_layers", 3))
    fusion_depth = int(training_cfg.get("fusion_depth", 2))

    if mode == "ast":
        from model.SingleBranch import ASTOnlyModel

        model: torch.nn.Module = ASTOnlyModel(
            ast_in=20,
            ast_edge_dim=1,
            hid=hid,
            out_classes=2,
            gnn_layers=gnn_layers,
        )
    elif mode == "dfg":
        from model.SingleBranch import DFGOnlyModel

        model = DFGOnlyModel(
            dfg_in=12,
            dfg_edge_dim=1,
            hid=hid,
            out_classes=2,
            gnn_layers=gnn_layers,
        )
    else:
        from model.CreativeGNN import DualStreamCrossGraphNet

        model = DualStreamCrossGraphNet(
            ast_in=20,
            ast_edge=1,
            dfg_in=12,
            dfg_edge=1,
            hid=hid,
            out_classes=2,
            gnn_layers=gnn_layers,
            fusion_depth=fusion_depth,
            use_ast=True,
            use_dfg=True,
        )

    # Find weights path from config, with sensible fallbacks
    training_meta = config.get("training_metadata", {})
    weights_path = training_meta.get("model_weights_path")
    if not weights_path:
        results_dir = training_meta.get("results_dir")
        if results_dir:
            weights_path = os.path.join(results_dir, "model.pt")
    if not weights_path:
        raise FileNotFoundError(
            "Model weights path not found in training configuration"
        )

    if not os.path.exists(weights_path):
        raise FileNotFoundError(f"Model weights not found at: {weights_path}")

    state = torch.load(weights_path, map_location=device)
    model.load_state_dict(state)
    model.to(str(device))
    model.eval()

    return model


def analyze_sample_with_model(
    model: torch.nn.Module,
    sample: Dict[str, Any],
    sample_id: str,
    device: Union[torch.device, str],
    mode: str = "both",
) -> Dict[str, Any]:
    """Analyze a single sample and return comprehensive results."""

    # Extract filename and function name
    filename, function_name = extract_filename_from_sample(sample)

    # Prepare graph data
    ast_data = None
    dfg_data = None

    if mode in ["both", "ast"] and "ast_graph" in sample:
        # Check if ast_graph is already a PyTorch Geometric Data object
        if hasattr(sample["ast_graph"], "x") and hasattr(
            sample["ast_graph"], "edge_index"
        ):
            # Already processed PyTorch Geometric Data object
            ast_data = sample["ast_graph"].to(str(device))
        else:
            # Raw data that needs processing
            from .explain import _build_pyg_from_ast_item

            ast_data = _build_pyg_from_ast_item(sample["ast_graph"]).to(str(device))
    if mode in ["both", "dfg"] and "dfg_graph" in sample:
        # Check if dfg_graph is already a PyTorch Geometric Data object
        if hasattr(sample["dfg_graph"], "x") and hasattr(
            sample["dfg_graph"], "edge_index"
        ):
            # Already processed PyTorch Geometric Data object
            dfg_data = sample["dfg_graph"].to(str(device))
        else:
            # Raw data that needs processing
            from .explain import _build_pyg_from_dfg_item

            dfg_data = _build_pyg_from_dfg_item(sample["dfg_graph"]).to(str(device))

    # Get prediction
    with torch.no_grad():
        if ast_data is not None and dfg_data is not None:
            logits = model(ast_data, dfg_data)
        elif ast_data is not None:
            logits = model(ast_data)
        elif dfg_data is not None:
            logits = model(dfg_data)
        else:
            raise ValueError("No valid graph data available")

        probs = torch.softmax(logits, dim=-1)
        predicted_label = logits.argmax(dim=-1).item()
        confidence = probs[0, predicted_label].item()

    # Get true label
    true_label = sample.get("label", 0)
    if isinstance(true_label, torch.Tensor):
        true_label = true_label.item()

    # Generate rationale analysis
    rationale = analyze_decision_rationale(
        model=model,
        ast_data=ast_data,
        dfg_data=dfg_data,
        positive_class=1,
        top_k_nodes=10,
        top_k_edges=10,
    )

    return {
        "sample_id": sample_id,
        "filename": filename,
        "function_name": function_name,
        "true_label": true_label,
        "predicted_label": predicted_label,
        "confidence": confidence,
        "correct_prediction": true_label == predicted_label,
        "rationale": rationale,
        "ast_data": ast_data,
        "dfg_data": dfg_data,
    }


def load_model_from_results(results_dir: str, device: torch.device, mode: str = "both"):
    """Load the trained model from results directory."""

    # Find model file
    model_path = None
    for filename in os.listdir(results_dir):
        if filename.endswith(".pt"):
            model_path = os.path.join(results_dir, filename)
            break

    if not model_path or not os.path.exists(model_path):
        raise FileNotFoundError(f"No model file found in {results_dir}")

    print(f"Loading model from: {model_path}")

    # Load model based on mode
    if mode == "ast":
        from model.SingleBranch import ASTOnlyModel

        model = ASTOnlyModel(
            ast_in=20, ast_edge_dim=1, hid=64, out_classes=2, gnn_layers=3
        )
    elif mode == "dfg":
        from model.SingleBranch import DFGOnlyModel

        model = DFGOnlyModel(
            dfg_in=12, dfg_edge_dim=1, hid=64, out_classes=2, gnn_layers=3
        )
    else:  # both
        from model.CreativeGNN import DualStreamCrossGraphNet

        model = DualStreamCrossGraphNet(
            ast_in=20,
            ast_edge=1,
            dfg_in=12,
            dfg_edge=1,
            hid=64,
            out_classes=2,
            gnn_layers=3,
            fusion_depth=2,
            use_ast=True,
            use_dfg=True,
        )

    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(str(device))
    model.eval()

    return model


def evaluate_model(
    model,
    dataloader,
    device: torch.device,
    max_samples: int = 100,
    mode: str = "both",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate model and generate comprehensive summary."""

    model.eval()
    sample_results = []
    classification_files = defaultdict(list)
    classification_functions = defaultdict(list)

    sample_count = 0

    print(f"Evaluating model on up to {max_samples} samples...")

    with torch.no_grad():
        for batch_idx, batch in enumerate(dataloader):
            if sample_count >= max_samples:
                break

            B = len(batch["label"])

            for i in range(B):
                if sample_count >= max_samples:
                    break

                sample_id = f"sample_{sample_count:04d}"

                # Create sample dict from batch
                sample = {
                    "ast_graph": (
                        batch["ast_graph"][i] if "ast_graph" in batch else None
                    ),
                    "dfg_graph": (
                        batch["dfg_graph"][i] if "dfg_graph" in batch else None
                    ),
                    "label": batch["label"][i],
                }

                # Add metadata from batch
                if "file" in batch and i < len(batch["file"]):
                    sample["file"] = batch["file"][i]
                if "path" in batch and i < len(batch["path"]):
                    sample["path"] = batch["path"][i]
                if "function" in batch and i < len(batch["function"]):
                    sample["function"] = batch["function"][i]

                # Add original data for human-friendly output
                if "ast_result_original_nodes" in batch and i < len(
                    batch["ast_result_original_nodes"]
                ):
                    sample["ast_result_original_nodes"] = batch[
                        "ast_result_original_nodes"
                    ][i]
                if "ast_result_original_edges" in batch and i < len(
                    batch["ast_result_original_edges"]
                ):
                    sample["ast_result_original_edges"] = batch[
                        "ast_result_original_edges"
                    ][i]
                if "dfg_result_original_nodes" in batch and i < len(
                    batch["dfg_result_original_nodes"]
                ):
                    sample["dfg_result_original_nodes"] = batch[
                        "dfg_result_original_nodes"
                    ][i]
                if "dfg_result_original_edges" in batch and i < len(
                    batch["dfg_result_original_edges"]
                ):
                    sample["dfg_result_original_edges"] = batch[
                        "dfg_result_original_edges"
                    ][i]

                try:
                    result = analyze_sample_with_model(
                        model=model,
                        sample=sample,
                        sample_id=sample_id,
                        device=device,
                        mode=mode,
                    )

                    # Get data objects from result
                    ast_data = result.get("ast_data")
                    dfg_data = result.get("dfg_data")

                    sample_results.append(result)

                    # Update classification lists
                    if result["filename"]:
                        classification_files[result["predicted_label"]].append(
                            result["filename"]
                        )
                    if result["function_name"]:
                        classification_functions[result["predicted_label"]].append(
                            result["function_name"]
                        )

                    # Save individual results if output directory is provided
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)

                        # Create a subdirectory per sample
                        sample_dir = os.path.join(output_dir, sample_id)
                        os.makedirs(sample_dir, exist_ok=True)

                        # Save rationale JSON (includes top nodes/edges/features)
                        save_decision_rationale(
                            out_dir=sample_dir,
                            rationale=result["rationale"],
                            sample_id=sample_id,
                            ast_data=ast_data,
                            dfg_data=dfg_data,
                            original_sample=sample,
                        )

                        # Save prediction metadata
                        metadata = {
                            "sample_id": sample_id,
                            "filename": result["filename"],
                            "function_name": result["function_name"],
                            "true_label": result["true_label"],
                            "predicted_label": result["predicted_label"],
                            "confidence": result["confidence"],
                            "correct_prediction": result["correct_prediction"],
                        }
                        with open(os.path.join(sample_dir, "metadata.json"), "w") as f:
                            json.dump(metadata, f, indent=2)

                        # Save full graphs (AST/DFG) tensors for further inspection
                        def serialize_graph(g):
                            if g is None:
                                return None
                            return {
                                "x": (
                                    g.x.detach().cpu().tolist()
                                    if hasattr(g, "x")
                                    else []
                                ),
                                "edge_index": (
                                    g.edge_index.detach().cpu().tolist()
                                    if hasattr(g, "edge_index")
                                    else []
                                ),
                                "edge_attr": (
                                    g.edge_attr.detach().cpu().tolist()
                                    if hasattr(g, "edge_attr")
                                    and g.edge_attr is not None
                                    else []
                                ),
                            }

                        graphs_payload = {
                            "ast_graph": serialize_graph(sample.get("ast_graph")),
                            "dfg_graph": serialize_graph(sample.get("dfg_graph")),
                        }
                        with open(os.path.join(sample_dir, "graphs.json"), "w") as f:
                            json.dump(graphs_payload, f, indent=2)

                    sample_count += 1

                    if sample_count % 10 == 0:
                        print(f"Processed {sample_count} samples...")

                except Exception as e:
                    print(f"Error processing sample {sample_id}: {e}")
                    continue

    if not sample_results:
        return {"error": "No samples processed"}

    # Generate summary statistics
    total_samples = len(sample_results)
    correct_predictions = sum(1 for r in sample_results if r["correct_prediction"])
    accuracy = correct_predictions / total_samples if total_samples > 0 else 0.0

    # Confidence statistics
    confidences = [r["confidence"] for r in sample_results]
    avg_confidence = np.mean(confidences) if confidences else 0.0
    min_confidence = np.min(confidences) if confidences else 0.0
    max_confidence = np.max(confidences) if confidences else 0.0

    # Classification distribution
    true_label_counts = defaultdict(int)
    predicted_label_counts = defaultdict(int)

    for result in sample_results:
        true_label_counts[result["true_label"]] += 1
        predicted_label_counts[result["predicted_label"]] += 1

    # Confusion matrix
    confusion_matrix = defaultdict(lambda: defaultdict(int))
    for result in sample_results:
        confusion_matrix[result["true_label"]][result["predicted_label"]] += 1

    # Per-class statistics
    class_stats = {}
    for class_label in set(true_label_counts.keys()) | set(
        predicted_label_counts.keys()
    ):
        class_samples = [
            r for r in sample_results if r["predicted_label"] == class_label
        ]
        class_confidences = [r["confidence"] for r in class_samples]

        class_stats[class_label] = {
            "count": len(class_samples),
            "avg_confidence": np.mean(class_confidences) if class_confidences else 0.0,
            "min_confidence": np.min(class_confidences) if class_confidences else 0.0,
            "max_confidence": np.max(class_confidences) if class_confidences else 0.0,
            "filenames": classification_files[class_label],
            "function_names": classification_functions[class_label],
        }

    # Top misclassified samples
    misclassified = [
        {
            "sample_id": r["sample_id"],
            "filename": r["filename"],
            "function_name": r["function_name"],
            "true_label": r["true_label"],
            "predicted_label": r["predicted_label"],
            "confidence": r["confidence"],
        }
        for r in sample_results
        if not r["correct_prediction"]
    ]

    # Sort by confidence (highest confidence misclassifications first)
    misclassified.sort(key=lambda x: x["confidence"], reverse=True)

    summary = {
        "evaluation_summary": {
            "total_samples": total_samples,
            "accuracy": accuracy,
            "correct_predictions": correct_predictions,
            "incorrect_predictions": total_samples - correct_predictions,
        },
        "confidence_statistics": {
            "average": avg_confidence,
            "minimum": min_confidence,
            "maximum": max_confidence,
            "std_deviation": np.std(confidences) if confidences else 0.0,
        },
        "classification_distribution": {
            "true_labels": dict(true_label_counts),
            "predicted_labels": dict(predicted_label_counts),
        },
        "confusion_matrix": {
            str(true_label): dict(predicted_counts)
            for true_label, predicted_counts in confusion_matrix.items()
        },
        "per_class_statistics": {
            str(class_label): stats for class_label, stats in class_stats.items()
        },
        "misclassified_samples": misclassified[:20],  # Top 20 misclassified
        "filename_availability": {
            "samples_with_filenames": sum(1 for r in sample_results if r["filename"]),
            "samples_with_function_names": sum(
                1 for r in sample_results if r["function_name"]
            ),
            "total_samples": total_samples,
        },
    }

    return summary


"""
Dataset loading and caching module.

This module provides unified dataset loading with automatic caching.
"""

import json
import os
import pickle
from glob import glob
from typing import Any, Dict, Iterator, Optional

import torch
from datasets import load_dataset
from torch.utils.data import DataLoader as TorchDataLoader
from torch.utils.data import IterableDataset


class UnifiedDatasetLoader:
    """Unified dataset loader supporting multiple data sources."""

    def __init__(self, data_source: str, max_samples: int = 1000):
        """
        Initialize the dataset loader.

        Args:
            data_source: Data source specification:
                - "hf:repo_id/split" for HuggingFace datasets
                - "cache:path/to/cache" for cached data
                - "json:path/to/file.json" for JSON files
                - "jsonl:path/to/file.jsonl" for JSONL files
            max_samples: Maximum number of samples to load
        """
        self.data_source = data_source
        self.max_samples = max_samples
        self.samples_processed = 0

    def create_dataset(self) -> IterableDataset[Dict[str, Any]]:
        """Create an IterableDataset based on the data source."""

        if self.data_source.startswith("hf:"):
            return self._create_hf_dataset()
        elif self.data_source.startswith("cache:"):
            return self._create_cache_dataset()
        elif self.data_source.startswith("json"):
            return self._create_json_dataset()
        else:
            raise ValueError(f"Unsupported data source: {self.data_source}")

    def _create_hf_dataset(self) -> IterableDataset[Dict[str, Any]]:
        """Create dataset from HuggingFace."""
        parts = self.data_source[3:].split("/")
        if len(parts) != 2:
            raise ValueError("HF data source should be 'hf:repo_id/split'")

        repo_id, split = parts

        class HFDataset(IterableDataset):
            def __init__(self, repo_id: str, split: str, max_samples: int):
                self.repo_id = repo_id
                self.split = split
                self.max_samples = max_samples
                self.samples_processed = 0

            def __iter__(self) -> Iterator[Dict[str, Any]]:
                dataset = load_dataset(self.repo_id, split=self.split, streaming=True)
                for sample in dataset:
                    if self.samples_processed >= self.max_samples:
                        break

                    # Type guard to ensure sample is a dictionary
                    if not isinstance(sample, dict):
                        continue

                    # Filter out samples without required data
                    if not sample.get("ast_result") or not sample.get("dfg_result"):
                        continue

                    # Convert to expected format
                    yield {
                        "ast_graph": sample["ast_result"],
                        "dfg_graph": sample["dfg_result"],
                        "label": torch.tensor(sample.get("label", 0), dtype=torch.long),
                        "file": sample.get("file", None),
                        "function": sample.get("function", None),
                    }

                    self.samples_processed += 1

        return HFDataset(repo_id, split, self.max_samples)

    def _create_cache_dataset(self) -> IterableDataset[Dict[str, Any]]:
        """Create dataset from cached data."""
        cache_dir = self.data_source[6:]  # Remove "cache:"

        class CachedDataset(IterableDataset):
            def __init__(self, cache_dir: str, max_samples: int):
                self.cache_dir = cache_dir
                self.max_samples = max_samples
                self.samples_processed = 0

            def __iter__(self) -> Iterator[Dict[str, Any]]:
                # Look for cached files
                cache_files = glob(os.path.join(self.cache_dir, "*.pkl"))
                if not cache_files:
                    raise FileNotFoundError(
                        f"No cached files found in {self.cache_dir}"
                    )

                for cache_file in cache_files:
                    if self.samples_processed >= self.max_samples:
                        break

                    with open(cache_file, "rb") as f:
                        samples = pickle.load(f)

                    for sample in samples:
                        if self.samples_processed >= self.max_samples:
                            break

                        yield sample
                        self.samples_processed += 1

        return CachedDataset(cache_dir, self.max_samples)

    def _create_json_dataset(self) -> IterableDataset[Dict[str, Any]]:
        """Create dataset from JSON/JSONL files."""
        file_path = self.data_source[5:]  # Remove "json:" or "jsonl:"

        class JsonDataset(IterableDataset):
            def __init__(self, json_file: str, max_samples: int):
                self.json_file = json_file
                self.max_samples = max_samples
                self.samples_processed = 0

            def __iter__(self) -> Iterator[Dict[str, Any]]:
                with open(self.json_file, "r") as f:
                    if self.json_file.endswith(".jsonl"):
                        # JSONL format
                        for line in f:
                            if self.samples_processed >= self.max_samples:
                                break

                            sample = json.loads(line.strip())
                            if self._is_valid_sample(sample):
                                yield self._convert_sample(sample)
                                self.samples_processed += 1
                    else:
                        # Regular JSON format
                        data = json.load(f)
                        for sample in data:
                            if self.samples_processed >= self.max_samples:
                                break

                            if self._is_valid_sample(sample):
                                yield self._convert_sample(sample)
                                self.samples_processed += 1

            def _is_valid_sample(self, sample):
                return (
                    sample.get("ast_graph") is not None
                    and sample.get("dfg_graph") is not None
                )

            def _convert_sample(self, sample):
                return {
                    "ast_graph": sample["ast_graph"],
                    "dfg_graph": sample["dfg_graph"],
                    "label": torch.tensor(sample.get("label", 0), dtype=torch.long),
                    "file": sample.get("file", None),
                    "function": sample.get("function", None),
                }

        return JsonDataset(file_path, self.max_samples)


def create_dataloader(
    repo_id: str,
    split: str = "test",
    max_samples: int = 1000,
    batch_size: int = 1,
    fresh: bool = False,
    **kwargs: Any,
) -> TorchDataLoader[Dict[str, Any]]:
    """
    Create a DataLoader from HuggingFace repository with automatic caching.

    Args:
        repo_id: HuggingFace repository ID (e.g., "org/dataset")
        split: Dataset split (train/test/validation) - default: "test"
        max_samples: Maximum number of samples to load
        batch_size: Batch size for the DataLoader
        fresh: If True, force fresh fetch from HuggingFace (ignore cache)
        **kwargs: Additional arguments for DataLoader

    Returns:
        TorchDataLoader instance
    """
    # Generate cache directory based on repo_id and split
    cache_dir = f"./cache/{repo_id.replace('/', '_')}_{split}"

    # Check if we should use cached data
    if not fresh and _is_cache_valid(repo_id, split, cache_dir, max_samples):
        print(f"Using cached data from {cache_dir}")
        data_source = f"cache:{cache_dir}"
    else:
        if fresh:
            print(f"Fresh fetch requested, ignoring cache")
        else:
            print(f"No valid cache found, fetching from HuggingFace")
        data_source = f"hf:{repo_id}/{split}"

    loader = UnifiedDatasetLoader(data_source, max_samples)
    dataset = loader.create_dataset()
    return TorchDataLoader(dataset, batch_size=batch_size, **kwargs)


def _is_cache_valid(repo_id: str, split: str, cache_dir: str, max_samples: int) -> bool:
    """Check if cached data is valid and sufficient."""
    if not os.path.exists(cache_dir):
        return False

    metadata_file = os.path.join(cache_dir, "metadata.json")
    if not os.path.exists(metadata_file):
        return False

    try:
        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        # Check if cache is for the same repo/split
        if metadata.get("repo_id") != repo_id or metadata.get("split") != split:
            return False

        # Check if cache has enough samples
        if metadata.get("total_samples", 0) < max_samples:
            return False

        # Check if cache files exist
        cache_files = glob(os.path.join(cache_dir, "*.pkl"))
        if not cache_files:
            return False

        return True
    except Exception:
        return False


def _invalidate_cache(cache_dir: str) -> None:
    """Invalidate cached data by removing cache directory."""
    if os.path.exists(cache_dir):
        import shutil

        shutil.rmtree(cache_dir)
        print(f"Cache invalidated: {cache_dir}")


def _cache_hf_dataset(
    repo_id: str,
    split: str,
    output_dir: str,
    max_samples: int = 1000,
    batch_size: int = 100,
) -> None:
    """
    Cache HuggingFace dataset for faster loading.

    Args:
        repo_id: HuggingFace repository ID
        split: Dataset split (train/test/validation)
        output_dir: Output directory for cached data
        max_samples: Maximum number of samples to cache
        batch_size: Batch size for caching
    """
    print(f"Caching data from {repo_id}/{split}")
    print(f"Max samples: {max_samples}")
    print(f"Output directory: {output_dir}")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Create dataset
    data_source = f"hf:{repo_id}/{split}"
    loader = UnifiedDatasetLoader(data_source, max_samples)
    dataset = loader.create_dataset()
    dataloader = TorchDataLoader(dataset, batch_size=batch_size)

    # Cache data in batches
    batch_count = 0
    total_samples = 0

    for batch in dataloader:
        batch_data = []

        # Process each sample in the batch
        for i in range(len(batch["label"])):
            sample = {
                "ast_graph": batch["ast_graph"][i],
                "dfg_graph": batch["dfg_graph"][i],
                "label": batch["label"][i],
                "file": batch["file"][i] if "file" in batch else None,
                "function": batch["function"][i] if "function" in batch else None,
            }
            batch_data.append(sample)

        # Save batch to file
        batch_file = os.path.join(output_dir, f"batch_{batch_count:04d}.pkl")
        with open(batch_file, "wb") as f:
            pickle.dump(batch_data, f)

        batch_count += 1
        total_samples += len(batch_data)

        print(
            f"Cached batch {batch_count}: {len(batch_data)} samples (total: {total_samples})"
        )

        if total_samples >= max_samples:
            break

    # Save metadata
    metadata = {
        "repo_id": repo_id,
        "split": split,
        "total_samples": total_samples,
        "batch_count": batch_count,
        "max_samples": max_samples,
    }

    metadata_file = os.path.join(output_dir, "metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nCaching completed!")
    print(f"Total samples cached: {total_samples}")
    print(f"Batches created: {batch_count}")
    print(f"Metadata saved to: {metadata_file}")


def cache_hf_dataset(
    repo_id: str,
    split: str = "test",
    max_samples: int = 1000,
    batch_size: int = 100,
    force: bool = False,
) -> None:
    """
    Cache HuggingFace dataset for faster loading with automatic cache management.

    Args:
        repo_id: HuggingFace repository ID
        split: Dataset split (train/test/validation) - default: "test"
        max_samples: Maximum number of samples to cache
        batch_size: Batch size for caching
        force: If True, force re-caching even if cache exists
    """
    # Generate cache directory based on repo_id and split
    cache_dir = f"./cache/{repo_id.replace('/', '_')}_{split}"

    if force and os.path.exists(cache_dir):
        _invalidate_cache(cache_dir)

    if not force and _is_cache_valid(repo_id, split, cache_dir, max_samples):
        print(f"Cache already exists and is valid: {cache_dir}")
        return

    _cache_hf_dataset(repo_id, split, cache_dir, max_samples, batch_size)


def extract_filename_from_sample(
    sample: Dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    """Extract filename and function name from sample data."""
    filename = None
    function_name = None

    # Try to extract from various possible fields
    if "file" in sample:
        filename = sample["file"]
    elif "path" in sample:
        filename = sample["path"]
    elif "filename" in sample:
        filename = sample["filename"]

    if "function" in sample:
        function_name = sample["function"]
    elif "function_name" in sample:
        function_name = sample["function_name"]

    # If we have a filename but no function name, try to extract from filename
    if filename and not function_name:
        function_name = os.path.splitext(os.path.basename(filename))[0]

    return filename, function_name
