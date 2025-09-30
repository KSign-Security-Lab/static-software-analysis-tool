#!/usr/bin/env python3
"""
Model evaluation script with automatic configuration loading.

Usage:
    python evaluate.py --results_dir ./results/.._.._data_test_121_full_1epochs
    python evaluate.py --results_dir ./results/.._.._data_test_121_full_1epochs --max_samples 100
    python evaluate.py --results_dir ./results/.._.._data_test_121_full_1epochs --device cuda:0
"""

import argparse
import json
import os
from typing import Any, Dict, Optional, Union

import torch
from dataset.JsonDataset import JsonDataset
from torch.utils.data import DataLoader as TorchDataLoader
from train import custom_collate_fn
from utils.evaluate import (
    create_model_from_config,
    evaluate_model,
    load_training_config,
)


def run_evaluation(
    results_dir: str,
    split: Optional[str] = None,
    max_samples: Optional[int] = None,
    device: Optional[str] = None,
    output_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run evaluation with automatic configuration loading.

    Args:
        results_dir: Results directory containing training configuration
        split: Dataset split (train/test) - if None, uses config default
        max_samples: Maximum samples to evaluate - if None, uses config default
        device: Device to use - if None, uses config default
        output_file: Output file name - if None, uses default

    Returns:
        Evaluation summary dictionary
    """
    # Load training configuration
    config = load_training_config(results_dir)

    # Use provided args or fall back to config defaults
    eval_defaults = config["evaluation_defaults"]
    training_config = config["training_config"]

    split = split or eval_defaults["split"]
    max_samples = max_samples or eval_defaults["max_samples"]
    device = device or eval_defaults["device"]
    output_file = output_file or "evaluation_summary.json"

    # Ensure all values are not None
    assert split is not None, "Split cannot be None"
    assert max_samples is not None, "Max samples cannot be None"
    assert device is not None, "Device cannot be None"
    assert output_file is not None, "Output file cannot be None"

    # Set device
    device_obj = torch.device(device)
    print(f"Using device: {device_obj}")

    # Create model from configuration
    model = create_model_from_config(config, device_obj)

    # Get data path from training config
    data_path = training_config["data_path"]
    print(f"Using data path: {data_path}")

    # Create evaluation dataset using JsonDataset
    print(f"Creating evaluation dataset from: {data_path}")

    # Load the dataset with JsonDataset
    if isinstance(data_path, list):
        dataset = JsonDataset(paths=data_path)
    else:
        dataset = JsonDataset(paths=[data_path])

    # Create dataloader (same as train script)
    dataloader = TorchDataLoader(
        dataset,
        batch_size=1,
        collate_fn=custom_collate_fn,
        num_workers=0,
        pin_memory=False,
        shuffle=False,  # No shuffling for evaluation
    )

    # Evaluate model
    print("Starting evaluation...")
    # Prepare per-sample output directory
    per_sample_out = os.path.join(results_dir, "evaluation")
    os.makedirs(per_sample_out, exist_ok=True)

    summary = evaluate_model(
        model=model,
        dataloader=dataloader,
        device=device_obj,
        max_samples=max_samples,
        mode=eval_defaults["mode"],
        output_dir=per_sample_out,
    )

    # Save summary
    summary_file = os.path.join(results_dir, output_file)
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nEvaluation completed!")
    print(f"Summary saved to: {summary_file}")

    # Print summary statistics
    print(f"\n=== Evaluation Results ===")
    print(f"Total samples: {summary['evaluation_summary']['total_samples']}")
    print(f"Accuracy: {summary['evaluation_summary']['accuracy']:.3f}")
    print(f"Average confidence: {summary['confidence_statistics']['average']:.3f}")

    filename_availability = summary["filename_availability"]
    print(
        f"Samples with filenames: {filename_availability['samples_with_filenames']}/{filename_availability['total_samples']}"
    )
    print(
        f"Samples with function names: {filename_availability['samples_with_function_names']}/{filename_availability['total_samples']}"
    )

    # Print classification files
    print(f"\nClassification Results:")
    for class_label, stats in summary["per_class_statistics"].items():
        print(
            f"Class {class_label}: {stats['count']} samples, {len(stats['filenames'])} files"
        )
        if stats["filenames"]:
            print(f"  Sample files: {stats['filenames'][:3]}...")  # Show first 3 files

    # Print misclassified samples
    misclassified = summary.get("misclassified_samples", [])
    if misclassified:
        print(f"\nTop Misclassified Samples ({len(misclassified)} total):")
        for i, sample in enumerate(misclassified[:5]):  # Show top 5
            print(
                f"  {i+1}. {sample.get('filename', 'N/A')} (function: {sample.get('function_name', 'N/A')})"
            )
            print(
                f"     True: {sample.get('true_label')}, Predicted: {sample.get('predicted_label')}, Confidence: {sample.get('confidence', 0.0):.3f}"
            )

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate trained GNN model with automatic configuration loading"
    )
    parser.add_argument(
        "--results_dir",
        type=str,
        required=True,
        help="Results directory containing training configuration",
    )
    parser.add_argument(
        "--split",
        type=str,
        choices=["train", "test"],
        help="Dataset split (overrides config default)",
    )
    parser.add_argument(
        "--max_samples",
        type=int,
        help="Maximum samples to evaluate (overrides config default)",
    )
    parser.add_argument(
        "--device", type=str, help="Device to use (overrides config default)"
    )
    parser.add_argument(
        "--output_file", type=str, help="Output file name (overrides default)"
    )

    args = parser.parse_args()

    # Run evaluation with automatic configuration
    run_evaluation(
        results_dir=args.results_dir,
        split=args.split,
        max_samples=args.max_samples,
        device=args.device,
        output_file=args.output_file,
    )


if __name__ == "__main__":
    main()
