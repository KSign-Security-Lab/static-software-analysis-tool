"""CPG Generator for converting source code to Code Property Graphs using Joern.

Supports C, C++, and Java source files via Joern's multi-language frontends.
"""

import json
import os
import shutil
import subprocess
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..types.cpg import CPGRoot, ICPGRootExport

# File extensions that Joern can process
SUPPORTED_EXTENSIONS = frozenset({
    ".c", ".h",                          # C
    ".cpp", ".cc", ".cxx", ".hpp", ".hxx",  # C++
    ".java",                              # Java
})


def is_supported_source_file(path: Path) -> bool:
    """Check if a file has a Joern-supported extension."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


class StandaloneCPGResult:
    """Result of CPG generation."""

    def __init__(self, cpg_data: CPGRoot, project_name: str, method_count: int):
        self.cpg_data = cpg_data
        self.project_name = project_name
        self.method_count = method_count


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
    """Worker function executed in a separate process.

    1. Copy the source file into a unique subdirectory under workspace/
    2. docker exec joern-parse
    3. docker exec joern-export
    4. Read the JSON result and write it to the output directory
    5. Clean up the workspace subdirectory
    """
    src = Path(source_file)
    in_root = Path(input_root)
    out_root = Path(output_root)
    ws = Path(workspace_dir)

    # Unique workspace subdirectory to avoid collisions between workers
    job_id = uuid.uuid4().hex[:12]
    job_dir = ws / f"job_{job_id}"

    try:
        # Preserve relative path structure
        try:
            rel_path = src.relative_to(in_root)
        except ValueError:
            rel_path = Path(src.name)

        # Copy source file into job directory
        job_source = job_dir / rel_path
        job_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, job_source)

        container_source = f"/workspace/job_{job_id}/{rel_path}"

        # Step 1: joern-parse
        parse_cmd = [
            "docker", "exec",
            "-w", f"/workspace/job_{job_id}",
            container_name,
            "/opt/joern/joern-cli/bin/joern-parse",
            container_source,
        ]
        parse_result = subprocess.run(
            parse_cmd, capture_output=True, text=True, timeout=300
        )
        if parse_result.returncode != 0:
            return {
                "success": False,
                "file": source_file,
                "error": f"joern-parse failed: {parse_result.stderr.strip()}",
            }

        # Verify cpg.bin was created
        cpg_bin = job_dir / "cpg.bin"
        if not cpg_bin.exists():
            return {
                "success": False,
                "file": source_file,
                "error": "cpg.bin not found after joern-parse",
            }

        # Step 2: joern-export
        export_cmd = [
            "docker", "exec",
            "-w", f"/workspace/job_{job_id}",
            container_name,
            "/opt/joern/joern-cli/bin/joern-export",
            f"--repr={representation}",
            f"--format={export_format}",
        ]
        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=300
        )
        if export_result.returncode != 0:
            return {
                "success": False,
                "file": source_file,
                "error": f"joern-export failed: {export_result.stderr.strip()}",
            }

        # Collect JSON output
        merged: Dict[str, Any] = {}

        # Check if stdout has JSON directly
        stdout = export_result.stdout.strip()
        if stdout.startswith("{"):
            try:
                merged = json.loads(stdout)
            except json.JSONDecodeError:
                pass

        # Otherwise read from the out/ directory
        if not merged:
            out_dir = job_dir / "out"
            if not out_dir.exists():
                return {
                    "success": False,
                    "file": source_file,
                    "error": "joern-export produced no output directory",
                }
            json_files = sorted(out_dir.rglob("*.json"))
            if not json_files:
                return {
                    "success": False,
                    "file": source_file,
                    "error": "No JSON files found in joern-export output",
                }
            for jf in json_files:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    merged.update(data)

        # Write result to output directory preserving structure
        output_file = out_root / rel_path.with_suffix(".json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")

        # Optionally copy the original source file alongside the JSON
        if copy_source:
            source_copy = out_root / rel_path
            source_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, source_copy)

        return {
            "success": True,
            "file": source_file,
            "output": str(output_file),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "file": source_file,
            "error": "Timed out (300s limit)",
        }
    except Exception as e:
        return {
            "success": False,
            "file": source_file,
            "error": str(e),
        }
    finally:
        # Clean up job directory
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
            capture_output=True, timeout=10,
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


class CPGGenerator:
    """Generator for Code Property Graphs using Joern."""

    async def convert_to_cpg_docker(
        self, input_data: str, options: Optional[Dict[str, Any]] = None
    ) -> StandaloneCPGResult:
        """Convert source code to CPG using Docker."""
        import asyncio

        if options is None:
            options = {}

        is_file_path = options.get("isFilePath", False)
        filename = options.get("filename")
        representation = options.get("repr", "all")
        export_format = options.get("format", "graphson")

        if is_file_path:
            source_file = input_data
            filename = filename or Path(input_data).name
        else:
            filename = filename or "main.c"
            import tempfile
            tmp_dir = Path(tempfile.gettempdir()) / f"joern-cpg-{uuid.uuid4()}"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            source_file = str(tmp_dir / filename)
            content = input_data if input_data.endswith("\n") else f"{input_data}\n"
            Path(source_file).write_text(content, encoding="utf-8")

        try:
            cpg_export = await self._generate_cpg_from_file_docker(
                source_file, representation=representation, export_format=export_format
            )

            project_name = f"c-src-{uuid.uuid4().hex[:8]}"
            method_count = self._count_methods(CPGRoot(export=cpg_export))

            return StandaloneCPGResult(
                cpg_data=CPGRoot(export=cpg_export),
                project_name=project_name,
                method_count=method_count,
            )
        finally:
            if not is_file_path:
                shutil.rmtree(Path(source_file).parent, ignore_errors=True)

    async def _generate_cpg_from_file_docker(
        self, source_file: str, representation: str = "all", export_format: str = "graphson"
    ) -> ICPGRootExport:
        """Generate CPG from a source file using Docker."""
        import asyncio

        username = os.getenv("USER") or os.getenv("USERNAME") or "user"
        container_name = f"ssat-joern-{username}"

        project_root = _find_project_root(Path.cwd())
        workspace_dir = project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        source_path = Path(source_file)

        # Use a unique job directory
        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace_dir / f"job_{job_id}"

        try:
            # Determine relative path
            try:
                relative_to_project = source_path.relative_to(project_root)
            except ValueError:
                relative_to_project = Path(source_path.name)

            job_source = job_dir / relative_to_project
            job_source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, job_source)

            container_work_dir = f"/workspace/job_{job_id}"
            container_source = f"{container_work_dir}/{relative_to_project}"

            # Ensure permissions
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "exec", container_name, "chmod", "-R", "777", "/workspace",
                    cwd="/",
                )
                await proc.wait()
            except Exception:
                pass

            # Step 1: joern-parse
            parse_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "-w", container_work_dir, container_name,
                "/opt/joern/joern-cli/bin/joern-parse", container_source,
                cwd="/",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            _, stderr = await parse_proc.communicate()
            if parse_proc.returncode != 0:
                raise RuntimeError(f"joern-parse failed: {stderr.decode('utf-8')}")

            cpg_bin = job_dir / "cpg.bin"
            if not cpg_bin.exists():
                raise RuntimeError("cpg.bin not found after joern-parse")

            # Step 2: joern-export
            export_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "-w", container_work_dir, container_name,
                "/opt/joern/joern-cli/bin/joern-export",
                f"--repr={representation}", f"--format={export_format}",
                cwd="/",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            stdout, stderr = await export_proc.communicate()
            if export_proc.returncode != 0:
                raise RuntimeError(f"joern-export failed: {stderr.decode('utf-8')}")

            # Process output
            stdout_str = stdout.decode("utf-8").strip()
            if stdout_str.startswith("{"):
                try:
                    return json.loads(stdout_str)  # type: ignore
                except json.JSONDecodeError:
                    pass

            out_dir = job_dir / "out"
            if not out_dir.exists():
                raise RuntimeError("joern-export produced no output directory")

            json_files = sorted(out_dir.rglob("*.json"))
            if not json_files:
                raise RuntimeError("No JSON files found in joern-export output")

            merged: Dict[str, Any] = {}
            for jf in json_files:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    merged.update(data)

            return merged  # type: ignore

        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    def _count_methods(self, cpg_data: CPGRoot) -> int:
        """Count methods in CPG data for validation."""
        try:
            export_data = cpg_data.export
            if isinstance(export_data, dict) and "method" in export_data:
                methods = export_data["method"]
                if isinstance(methods, list):
                    return len(methods)
        except Exception:
            pass
        return 0


def _find_project_root(start_dir: Path) -> Path:
    """Find the project root by looking for pyproject.toml or package.json."""
    current = start_dir
    while current != current.parent:
        if (current / "pyproject.toml").exists() or (current / "package.json").exists():
            return current
        current = current.parent
    return Path.cwd()
