"""Parallel batch CPG generation over a source tree.

Single-file generation lives in :mod:`ssat.cpg.backends`; this module is the
process-pool driver on top of it. Supports C, C++, and Java via Joern's
multi-language frontends.

Each worker starts its own JVM and keeps it warm for every file it is handed,
which is the whole reason this is a process pool and not a thread pool: one JVM
cannot be shared across processes, and Joern's frontends are not re-entrant
within one. `spawn` rather than the default `fork`, because forking a process
that has already started a JVM gives the child a JVM it cannot use.

One thing the container path had that this does not: a per-file timeout. It
passed `timeout=300` to `docker exec` and reported a hung file as a failed one.
A JVM call in this process cannot be interrupted that way -- the only way back
is killing the worker, which a `ProcessPoolExecutor` task cannot do to itself.
A file Joern will not finish therefore stalls its worker rather than being
reported, and the other workers carry on.
"""

import json
import multiprocessing
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from .backends import EmbeddedBackend

# File extensions that Joern can process
SUPPORTED_EXTENSIONS = frozenset(
    {
        ".c",
        ".h",  # C
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hxx",  # C++
        ".java",  # Java
    }
)


def is_supported_source_file(path: Path) -> bool:
    """Check if a file has a Joern-supported extension."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _relative_source_path(src: Path, input_root: Path) -> Path:
    """Return the source path relative to a directory input, or just the filename."""
    if input_root.is_file():
        return Path(src.name)
    try:
        rel_path = src.relative_to(input_root)
    except ValueError:
        return Path(src.name)
    return Path(src.name) if rel_path == Path(".") else rel_path


def _cpg_json_output_path(output_root: Path, rel_source_path: Path) -> Path:
    """Build a collision-resistant CPG JSON path, preserving the source suffix."""
    return output_root / rel_source_path.parent / f"{rel_source_path.name}.json"


# ---------------------------------------------------------------------------
# Multiprocess batch generation (simple shared-volume approach)
# ---------------------------------------------------------------------------


def _worker_generate_one(
    source_file: str,
    input_root: str,
    output_root: str,
    representation: str,
    copy_source: bool = False,
) -> Dict[str, Any]:
    """Generate one CPG in a worker process and write it to the output tree.

    The JVM is started lazily by the first file this worker takes and reused by
    the rest, so the cost is once per worker rather than once per file.
    """
    src = Path(source_file)
    out_root = Path(output_root)

    try:
        rel_path = _relative_source_path(src, Path(input_root))
        result = EmbeddedBackend().generate_file(src, representation=representation)

        output_file = _cpg_json_output_path(out_root, rel_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(result.graphson, indent=2), encoding="utf-8")

        if copy_source:
            source_copy = out_root / rel_path
            source_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, source_copy)

        return {"success": True, "file": source_file, "output": str(output_file)}

    except Exception as exc:  # noqa: BLE001 - reported per-file, never kills the batch
        return {"success": False, "file": source_file, "error": str(exc)}


def batch_generate_cpg(
    files: List[Path],
    input_root: Path,
    output_root: Path,
    workers: int = 4,
    representation: str = "all",
    copy_source: bool = False,
    progress_callback: Any = None,
) -> List[Dict[str, Any]]:
    """Generate CPGs for multiple files, one JVM per worker process.

    Args:
        files: Source files to process
        input_root: Root directory of the input (for computing relative paths)
        output_root: Where to write the JSON results
        workers: Number of parallel worker processes, each with its own JVM
        representation: Joern representation (ast, cfg, cpg14, all)
        copy_source: If True, copy original source files alongside JSON output
        progress_callback: Optional callable(result_dict) for progress updates
    """
    results: List[Dict[str, Any]] = []

    # See the module docstring: fork would hand a child a JVM it cannot use.
    context = multiprocessing.get_context("spawn")

    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as executor:
        future_to_file = {
            executor.submit(
                _worker_generate_one,
                str(f),
                str(input_root),
                str(output_root),
                representation,
                copy_source,
            ): f
            for f in files
        }

        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            if progress_callback:
                progress_callback(result)

    return results
