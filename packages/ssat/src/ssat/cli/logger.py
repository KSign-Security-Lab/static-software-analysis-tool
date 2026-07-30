"""Simple logger with progress bar support."""

import os
import sys
from typing import Any, Dict, Optional

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


class SimpleLogger:
    """Simple logger with progress bar support."""

    def __init__(self, debug_mode: bool = False):
        """Initialize logger."""
        self.is_debug_mode = debug_mode or bool(os.getenv("DEBUG"))
        self.progress_bar: Optional[tqdm] = None

    def info(self, message: str) -> None:
        """Log info message."""
        if self.progress_bar:
            self.progress_bar.close()
            self.progress_bar = None
        print(f"[INFO] {message}", file=sys.stdout)

    def info_keep_progress(self, message: str) -> None:
        """Log info message without stopping progress bar."""
        print(f"[INFO] {message}", file=sys.stdout)

    def error(self, message: str) -> None:
        """Log error message."""
        if self.progress_bar:
            self.progress_bar.close()
            self.progress_bar = None
        print(f"[ERROR] {message}", file=sys.stderr)

    def debug(self, message: str) -> None:
        """Log debug message."""
        if self.is_debug_mode:
            if self.progress_bar:
                self.progress_bar.close()
                self.progress_bar = None
            print(f"[DEBUG] {message}", file=sys.stdout)

    def start_progress(self, total: int, start_value: int = 0) -> None:
        """Start progress bar."""
        if tqdm is not None:
            self.progress_bar = tqdm(
                total=total,
                initial=start_value,
                desc="Progress",
                unit="files",
                bar_format="{l_bar}{bar}| {percentage:3.0f}% | {n_fmt}/{total_fmt} files | ETA: {remaining}",
            )

    def update_progress(self, value: int, payload: Optional[Dict[str, Any]] = None) -> None:
        """Update progress bar."""
        if self.progress_bar:
            self.progress_bar.update(value - self.progress_bar.n)

    def stop_progress(self) -> None:
        """Stop progress bar."""
        if self.progress_bar:
            self.progress_bar.close()
            self.progress_bar = None
