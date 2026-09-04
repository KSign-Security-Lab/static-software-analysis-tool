"""Simple logger with progress bar support."""

import os
import sys
from typing import Any, Dict, Optional

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


class SimpleLogger:
    """Log lines and a progress bar that coexist on one terminal.

    Every message used to ``close()`` the bar and drop the reference, and
    nothing ever reopened it -- so a single per-file error partway through a
    batch removed the bar for the rest of the run. ``tqdm.write`` exists for
    exactly this: it clears the bar, writes the line, and redraws underneath.
    """

    def __init__(self, debug_mode: bool = False):
        """Initialize logger."""
        self.is_debug_mode = debug_mode or bool(os.getenv("DEBUG"))
        self.progress_bar: Optional[tqdm] = None

    def info(self, message: str) -> None:
        """Log info message."""
        self._write(f"[INFO] {message}", sys.stdout)

    def info_keep_progress(self, message: str) -> None:
        """Log info message without stopping progress bar.

        Kept as a distinct name for callers that predate :meth:`info` learning
        to leave the bar alone; the two behave the same now.
        """
        self._write(f"[INFO] {message}", sys.stdout)

    def error(self, message: str) -> None:
        """Log error message."""
        self._write(f"[ERROR] {message}", sys.stderr)

    def debug(self, message: str) -> None:
        """Log debug message."""
        if self.is_debug_mode:
            self._write(f"[DEBUG] {message}", sys.stdout)

    def _write(self, line: str, stream: Any) -> None:
        """Emit one line without tearing the progress bar."""
        if self.progress_bar is not None and tqdm is not None:
            tqdm.write(line, file=stream)
        else:
            print(line, file=stream)

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
