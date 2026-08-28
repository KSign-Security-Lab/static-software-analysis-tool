"""Parallel batch CPG generation over a source tree.

Single-file generation lives in :mod:`ssat.cpg.backends`; this module is the
process-pool driver on top of it. Supports C, C++, and Java via Joern's
multi-language frontends.
"""

import json
import shutil
import subprocess
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from .backends import run_joern_in_container

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
    container_name: str,
    workspace_dir: str,
    representation: str,
    export_format: str,
    copy_source: bool = False,
) -> Dict[str, Any]:
    """Generate one CPG in a worker process and write it to the output tree.

    The docker invocation itself lives in :func:`ssat.cpg.backends.run_joern_in_container`,
    shared with the single-file path.
    """
    src = Path(source_file)
    out_root = Path(output_root)
    job_id = uuid.uuid4().hex[:12]
    job_dir = Path(workspace_dir) / f"job_{job_id}"

    try:
        rel_path = _relative_source_path(src, Path(input_root))
        job_source = job_dir / rel_path
        job_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, job_source)

        graphson = run_joern_in_container(
            job_dir,
            f"/workspace/job_{job_id}/{rel_path}",
            f"/workspace/job_{job_id}",
            container_name=container_name,
            representation=representation,
            export_format=export_format,
        )

        output_file = _cpg_json_output_path(out_root, rel_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(graphson, indent=2), encoding="utf-8")

        if copy_source:
            source_copy = out_root / rel_path
            source_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, source_copy)

        return {"success": True, "file": source_file, "output": str(output_file)}

    except subprocess.TimeoutExpired:
        return {"success": False, "file": source_file, "error": "Timed out (300s limit)"}
    except Exception as exc:  # noqa: BLE001 - reported per-file, never kills the batch
        return {"success": False, "file": source_file, "error": str(exc)}
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def batch_generate_cpg(
    files: List[Path],
    input_root: Path,
    output_root: Path,
    container_name: str,
    workers: int = 4,
    representation: str = "all",
    export_format: str = "graphson",
    copy_source: bool = False,
    progress_callback: Any = None,
) -> List[Dict[str, Any]]:
    """Generate CPGs for multiple files using multiprocessing.

    Each worker runs joern-parse + joern-export via docker exec in its own
    unique workspace subdirectory to avoid file collisions.

    Args:
        files: Source files to process
        input_root: Root directory of the input (for computing relative paths)
        output_root: Where to write the JSON results
        container_name: Docker container name running Joern
        workers: Number of parallel workers
        representation: Joern representation (ast, cfg, cpg14, all)
        export_format: Joern export format (graphson, dot, graphml)
        copy_source: If True, copy original source files alongside JSON output
        progress_callback: Optional callable(result_dict) for progress updates
    """
    # Find the project root to locate the workspace directory
    project_root = _find_project_root(Path.cwd())
    workspace_dir = project_root / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Ensure workspace has correct permissions in Docker
    try:
        subprocess.run(
            ["docker", "exec", container_name, "chmod", "-R", "777", "/workspace"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass

    results: List[Dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_file = {
            executor.submit(
                _worker_generate_one,
                str(f),
                str(input_root),
                str(output_root),
                container_name,
                str(workspace_dir),
                representation,
                export_format,
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


# ---------------------------------------------------------------------------
# Single-file generation (used by downstream template/ast/dfg pipeline)
# ---------------------------------------------------------------------------


def _find_project_root(start_dir: Path) -> Path:
    """Find the project root by looking for pyproject.toml or package.json."""
    current = start_dir
    while current != current.parent:
        if (current / "pyproject.toml").exists() or (current / "package.json").exists():
            return current
        current = current.parent
    return Path.cwd()
