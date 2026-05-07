"""CPG Generator for converting C source code to Code Property Graphs using Joern."""

import asyncio
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from ..types.cpg import CPGRoot, ICPGRootExport


class StandaloneCPGResult:
    """Result of CPG generation."""

    def __init__(self, cpg_data: CPGRoot, project_name: str, method_count: int):
        self.cpg_data = cpg_data
        self.project_name = project_name
        self.method_count = method_count


class CPGGenerator:
    """Generator for Code Property Graphs using Joern."""

    async def convert_to_cpg_standalone(
        self, c_source: str, options: Optional[Dict[str, Any]] = None
    ) -> StandaloneCPGResult:
        """Convert C source code to CPG using standalone Joern."""
        if options is None:
            options = {}
        filename = options.get("filename", "main.c")

        if not filename.endswith(".c"):
            raise ValueError(f'filename must end with ".c": received "{filename}"')

        # Create temporary directory
        tmp_dir = Path(tempfile.gettempdir()) / f"joern-cpg-{uuid.uuid4()}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Write C source to temporary file
            source_file = tmp_dir / filename
            content = c_source if c_source.endswith("\n") else f"{c_source}\n"
            source_file.write_text(content, encoding="utf-8")

            # Generate CPG using joern-parse and joern-export
            cpg_export = await self._generate_cpg_from_file(str(source_file))

            # Generate project name
            project_name = f"c-src-{uuid.uuid4().hex[:8]}"

            # Count methods for validation
            method_count = self._count_methods(CPGRoot(export=cpg_export))

            return StandaloneCPGResult(
                cpg_data=CPGRoot(export=cpg_export),
                project_name=project_name,
                method_count=method_count,
            )
        finally:
            # Clean up temporary directory
            try:
                import shutil

                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    async def _generate_cpg_from_file(self, source_file: str) -> ICPGRootExport:
        """Generate CPG from a source file."""
        tmp_dir = Path(source_file).parent

        # Step 1: joern-parse
        parse_result = await self._run_joern_parse(source_file, str(tmp_dir))
        if not parse_result["success"]:
            raise RuntimeError(f"joern-parse failed: {parse_result.get('error', 'Unknown error')}")

        # Check if cpg.bin was created
        cpg_path = tmp_dir / "cpg.bin"
        if not cpg_path.exists():
            raise RuntimeError("cpg.bin not found after joern-parse")

        # Step 2: joern-export
        export_result = await self._run_joern_export(str(tmp_dir))
        if not export_result["success"]:
            raise RuntimeError(f"joern-export failed: {export_result.get('error', 'Unknown error')}")

        # Process export result
        data = export_result.get("data")
        if data and isinstance(data, dict) and "outDir" not in data:
            return data  # type: ignore

        # Merge JSON files from output directory
        out_dir = tmp_dir / "out"
        if not out_dir.exists():
            raise RuntimeError("joern-export produced no output directory")

        json_files = [f for f in out_dir.iterdir() if f.suffix.lower() == ".json"]
        if not json_files:
            raise RuntimeError("No JSON files found in joern-export output")

        # Merge all JSON files
        merged: Dict[str, Any] = {}
        for json_file in json_files:
            content = json_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                merged.update(data)

        return merged  # type: ignore

    async def _run_joern_parse(self, source_file: str, cwd: str) -> Dict[str, Any]:
        """Run joern-parse command."""
        process = await asyncio.create_subprocess_exec(
            "joern-parse",
            source_file,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "error": stderr.decode("utf-8") if process.returncode != 0 else None,
        }

    async def _run_joern_export(self, cwd: str) -> Dict[str, Any]:
        """Run joern-export command."""
        process = await asyncio.create_subprocess_exec(
            "joern-export",
            "--repr=all",
            "--format=graphson",
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode("utf-8") or f"joern-export exited with code {process.returncode}",
            }

        stdout_str = stdout.decode("utf-8").strip()
        if stdout_str.startswith("{"):
            try:
                parsed = json.loads(stdout_str)
                return {"success": True, "data": parsed}
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Invalid JSON from stdout: {e}"}
        else:
            return {"success": True, "data": {"outDir": str(Path(cwd) / "out")}}

    async def convert_to_cpg_docker(
        self, input_data: str, options: Optional[Dict[str, Any]] = None
    ) -> StandaloneCPGResult:
        """Convert C source code to CPG using Docker."""
        if options is None:
            options = {}

        is_file_path = options.get("isFilePath", False)
        filename = options.get("filename")

        if is_file_path:
            source_file = input_data
            filename = filename or Path(input_data).name
        else:
            filename = filename or "main.c"
            if not filename.endswith(".c"):
                raise ValueError(f'filename must end with ".c": received "{filename}"')

            # Create temporary directory
            tmp_dir = Path(tempfile.gettempdir()) / f"joern-cpg-{uuid.uuid4()}"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            # Write C source to temporary file
            source_file = str(tmp_dir / filename)
            content = input_data if input_data.endswith("\n") else f"{input_data}\n"
            Path(source_file).write_text(content, encoding="utf-8")

        try:
            # Generate CPG using Docker
            cpg_export = await self._generate_cpg_from_file_docker(source_file)

            # Generate project name
            project_name = f"c-src-{uuid.uuid4().hex[:8]}"

            # Count methods for validation
            method_count = self._count_methods(CPGRoot(export=cpg_export))

            return StandaloneCPGResult(
                cpg_data=CPGRoot(export=cpg_export),
                project_name=project_name,
                method_count=method_count,
            )
        finally:
            # Clean up temporary directory only if we created it
            if not is_file_path:
                try:
                    import shutil

                    shutil.rmtree(Path(source_file).parent, ignore_errors=True)
                except Exception:
                    pass

    async def _generate_cpg_from_file_docker(self, source_file: str) -> ICPGRootExport:
        """Generate CPG from a source file using Docker."""
        username = os.getenv("USER") or os.getenv("USERNAME") or "user"
        container_name = f"ssat-joern-{username}"

        project_root = self._find_project_root(Path.cwd())
        workspace_dir = project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        source_path = Path(source_file)
        relative_to_project = source_path.relative_to(project_root)
        workspace_source_file = workspace_dir / relative_to_project
        workspace_source_file.parent.mkdir(parents=True, exist_ok=True)

        # Copy file to workspace
        import shutil

        shutil.copy2(source_path, workspace_source_file)

        # Clean up previous outputs
        (workspace_dir / "cpg.bin").unlink(missing_ok=True)
        shutil.rmtree(workspace_dir / "out", ignore_errors=True)

        # Also clean up inside Docker container
        try:
            await asyncio.create_subprocess_exec(
                "docker",
                "exec",
                container_name,
                "rm",
                "-rf",
                "/workspace/cpg.bin",
                "/workspace/out",
                cwd=str(workspace_dir),
            )
        except Exception:
            pass

        # Step 1: joern-parse via Docker
        relative_path = workspace_source_file.relative_to(workspace_dir)
        parse_result = await self._run_joern_parse_docker(
            container_name, f"/workspace/{relative_path}", str(workspace_dir)
        )
        if not parse_result["success"]:
            raise RuntimeError(f"joern-parse failed: {parse_result.get('error', 'Unknown error')}")

        # Check if cpg.bin was created
        cpg_path = workspace_dir / "cpg.bin"
        if not cpg_path.exists():
            raise RuntimeError("cpg.bin not found after joern-parse")

        # Step 2: joern-export via Docker
        export_result = await self._run_joern_export_docker(container_name, str(workspace_dir))
        if not export_result["success"]:
            raise RuntimeError(f"joern-export failed: {export_result.get('error', 'Unknown error')}")

        # Process export result
        data = export_result.get("data")
        if data and isinstance(data, dict) and "outDir" not in data:
            return data  # type: ignore

        # Merge JSON files from output directory
        out_dir = workspace_dir / "out"
        if not out_dir.exists():
            raise RuntimeError("joern-export produced no output directory")

        json_files = [f for f in out_dir.iterdir() if f.suffix.lower() == ".json"]
        if not json_files:
            raise RuntimeError("No JSON files found in joern-export output")

        # Merge all JSON files
        merged: Dict[str, Any] = {}
        for json_file in json_files:
            content = json_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                merged.update(data)

        return merged  # type: ignore

    async def _run_joern_parse_docker(
        self, container_name: str, source_path: str, cwd: str
    ) -> Dict[str, Any]:
        """Run joern-parse via Docker."""
        process = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            container_name,
            "/opt/joern/joern-cli/bin/joern-parse",
            source_path,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "error": stderr.decode("utf-8") if process.returncode != 0 else None,
        }

    async def _run_joern_export_docker(self, container_name: str, cwd: str) -> Dict[str, Any]:
        """Run joern-export via Docker."""
        process = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            container_name,
            "/opt/joern/joern-cli/bin/joern-export",
            "--repr=all",
            "--format=graphson",
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode("utf-8") or f"joern-export exited with code {process.returncode}",
            }

        stdout_str = stdout.decode("utf-8").strip()
        if stdout_str.startswith("{"):
            try:
                parsed = json.loads(stdout_str)
                return {"success": True, "data": parsed}
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Invalid JSON from stdout: {e}"}
        else:
            return {"success": True, "data": {"outDir": str(Path(cwd) / "out")}}

    def _find_project_root(self, start_dir: Path) -> Path:
        """Find the project root by looking for package.json with workspaces."""
        current = start_dir
        while current != current.parent:
            package_json = current / "package.json"
            if package_json.exists():
                try:
                    data = json.loads(package_json.read_text(encoding="utf-8"))
                    if "workspaces" in data:
                        return current
                except Exception:
                    pass
            current = current.parent
        return Path.cwd()

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

