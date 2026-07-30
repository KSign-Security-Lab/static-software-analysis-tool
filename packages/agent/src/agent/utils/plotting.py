from __future__ import annotations

from typing import List, Optional

import math
import os
import matplotlib.pyplot as plt


def _downsample_series(y: List[float], max_points: Optional[int]) -> tuple[List[int], List[float]]:
    n = len(y)
    if n == 0:
        return [], []
    if not max_points or max_points <= 0 or n <= max_points:
        return list(range(1, n + 1)), y
    stride = max(1, math.ceil(n / max_points))
    xs = list(range(1, n + 1, stride))
    ys = [y[i - 1] for i in xs]
    return xs, ys


def draw_loss_plot(
    results_dir: str,
    iteration_losses: List[float],
    epoch_avg_losses: List[float],
    *,
    max_points: Optional[int] = None,
    title: str = "Training Loss (All)",
) -> str:
    """Render loss curves to loss.png in results_dir.

    - Downsamples iteration curve to at most `max_points` by uniform stride.
    - Leaves epoch average points as-is.
    Returns the output path.
    """
    os.makedirs(results_dir, exist_ok=True)
    out_path = os.path.join(results_dir, "loss.png")

    plt.figure(figsize=(7, 4.5))

    if iteration_losses:
        xs, ys = _downsample_series(iteration_losses, max_points)
        plt.plot(xs, ys, label="train (iter)", linewidth=1.2)

    if epoch_avg_losses:
        # Plot at evenly spaced positions along the x-axis based on downsample stride
        # This keeps a rough alignment with iteration scale without requiring dataloader length.
        ex = list(range(1, len(epoch_avg_losses) + 1))
        plt.plot(ex, epoch_avg_losses, marker="o", linestyle="--", label="epoch avg")

    plt.xlabel("Iteration")
    plt.ylabel("Loss")
    plt.title(title)
    plt.grid(True, linestyle="--", alpha=0.35)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return out_path
