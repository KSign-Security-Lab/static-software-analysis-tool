"""Main entry point for SSAT CLI."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from .logger import SimpleLogger
from .parser import CliOptions, CliParser

# Import core functions
try:
    from ssat.endpoint import generate_ast, generate_cpg, generate_dfg, generate_template
    from ssat.cpg.generator import batch_generate_cpg, SUPPORTED_EXTENSIONS
except ImportError:
    # Fallback if core is not installed
    SUPPORTED_EXTENSIONS = frozenset({".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".java"})

    def batch_generate_cpg(*args, **kwargs):
        raise NotImplementedError("Core package not available")

    def generate_cpg(*args, **kwargs):
        raise NotImplementedError("Core package not available")

    def generate_template(*args, **kwargs):
        raise NotImplementedError("Core package not available")

    def generate_ast(*args, **kwargs):
        raise NotImplementedError("Core package not available")

    def generate_dfg(*args, **kwargs):
        raise NotImplementedError("Core package not available")


def find_monorepo_root(start_dir: Path) -> Path:
    """Find monorepo root by looking for pyproject.toml."""
    current = start_dir
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


def resolve_input_path(data_path: str) -> Path:
    """Resolve input path."""
    path = Path(data_path)
    if path.is_absolute():
        return path
    # Try relative to current directory
    if path.exists():
        return path.resolve()
    # Try relative to monorepo root
    repo_root = find_monorepo_root(Path.cwd())
    repo_path = repo_root / data_path
    if repo_path.exists():
        return repo_path.resolve()
    return path.resolve()


def collect_files_recursively(
    root_path: Path, predicate, fs_module, path_module
) -> List[Path]:
    """Collect files recursively matching predicate."""
    files = []
    if root_path.is_file():
        if predicate(str(root_path)):
            files.append(root_path)
    elif root_path.is_dir():
        for item in root_path.rglob("*"):
            if item.is_file() and predicate(str(item)):
                files.append(item)
    return files


def sanitize_token(s: str) -> str:
    """Sanitize filename token."""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in s)[:100]


def extract_name_from_code(code: str | None, fallback: str) -> str:
    """Extract function name from code."""
    if not code:
        return fallback
    # Extract name similar to Node.js version
    m = code.split("<entry:")[-1] if "<entry:" in code else code
    for sep in ["_", "(", ")", "[", "]", "{", "}", ":", ";", ",", ".", "?", "!", "|", "&", "^", "~", "`", "'", '"', " ", "\n", "\t", "\r", "\b", "\f"]:
        m = m.split(sep)[-1]
    return sanitize_token(m) if m else fallback


async def process_single_file(
    file_path: Path,
    input_root: Path,
    output_root: Path,
    options: CliOptions,
    logger: SimpleLogger,
) -> None:
    """Process a single file."""
    is_source_file = file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    cpg = None

    try:
        if is_source_file:
            cpg = await generate_cpg(
                str(file_path),
                "file",
                representation=options.representation,
                export_format=options.export_format,
            )
        else:
            # Assume JSON file with CPG data
            cpg = json.loads(file_path.read_text(encoding="utf-8"))

        result: Any = None

        if options.mode == "cpg":
            result = cpg
        elif options.mode == "template":
            result = generate_template(cpg)
        elif options.mode == "ast":
            template = generate_template(cpg)
            result = await generate_ast(template)
        elif options.mode == "dfg":
            template = generate_template(cpg)
            ast = await generate_ast(template)
            result = generate_dfg(cpg, ast)
        elif options.mode == "full":
            template = generate_template(cpg)
            ast = await generate_ast(template)
            dfg = generate_dfg(cpg, ast)
            result = {"ast": ast, "dfg": dfg}
        elif options.mode == "template-functions":
            template = generate_template(cpg)
            from ssat.ast.utils import recursively_get_functions_from_template
            result = recursively_get_functions_from_template(template)

        # Write result
        if result is not None:
            base = file_path.stem
            relative = file_path.relative_to(input_root) if file_path.is_relative_to(input_root) else file_path
            out_dir = output_root / relative.parent
            out_dir.mkdir(parents=True, exist_ok=True)

            # Handle per-function outputs for certain modes
            if options.mode in ("ast", "template-functions", "dfg", "full"):
                if options.mode == "ast":
                    ast_array = result if isinstance(result, list) else []
                    for idx, ast_item in enumerate(ast_array):
                        func_name = extract_name_from_code(
                            ast_item.get("nodes", [{}])[0].get("code") if ast_item.get("nodes") else None,
                            f"func_{idx}",
                        )
                        per_func_file = out_dir / f"{base}_{func_name}_{options.mode}.json"
                        per_func_file.write_text(json.dumps(ast_item, indent=2), encoding="utf-8")
                elif options.mode == "template-functions":
                    funcs = result if isinstance(result, list) else []
                    for i, fn in enumerate(funcs):
                        fn_name = extract_name_from_code(fn.get("name") if isinstance(fn, dict) else None, f"func_{i}")
                        per_func_file = out_dir / f"{base}_{fn_name}_{options.mode}.json"
                        per_func_file.write_text(json.dumps(fn, indent=2), encoding="utf-8")
                elif options.mode == "dfg":
                    dfgs = result if isinstance(result, list) else []
                    for i, dfg in enumerate(dfgs):
                        nodes = dfg.get("nodes", []) if isinstance(dfg, dict) else []
                        debug_code = nodes[0].get("debug", {}).get("callName") if nodes else None
                        fn_name = extract_name_from_code(debug_code, f"func_{i}")
                        per_func_file = out_dir / f"{base}_{fn_name}_{options.mode}.json"
                        per_func_file.write_text(json.dumps(dfg, indent=2), encoding="utf-8")
                elif options.mode == "full":
                    full_result = result if isinstance(result, dict) else {}
                    ast_data = full_result.get("ast", [])
                    dfg_data = full_result.get("dfg", [])
                    if len(ast_data) != len(dfg_data):
                        raise RuntimeError("AST and DFG results must have the same length")
                    for idx, ast_item in enumerate(ast_data):
                        function_node = ast_item.get("nodes", [{}])[0] if ast_item.get("nodes") else {}
                        func_name = extract_name_from_code(function_node.get("code"), f"func_{idx}")
                        per_func_file = out_dir / f"{base}_{func_name}_{options.mode}.json"
                        save_obj = {
                            "file": func_name,
                            "label": 1 if "bad" in func_name.lower() else 0,
                            "ast_result": ast_item,
                            "dfg_result": dfg_data[idx] if idx < len(dfg_data) else {},
                        }
                        per_func_file.write_text(json.dumps(save_obj, indent=2), encoding="utf-8")
            else:
                # Single file output for other modes
                output_file = out_dir / f"{base}_{options.mode}.json"
                output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        if options.debug:
            import traceback

            traceback.print_exc()


async def main() -> None:
    """Main entry point."""
    parser = CliParser()
    options = parser.parse()

    logger = SimpleLogger(options.debug)

    logger.info("Static Software Analysis Tool (SSAT) v2.4.3")
    logger.info(f"Mode: {options.mode}")
    logger.info(f"Input: {options.data}")

    # Determine output path
    workspace_root = find_monorepo_root(Path.cwd())
    raw_output = options.output or f"result/{options.mode}_{int(__import__('time').time())}"
    output_path = Path(raw_output) if Path(raw_output).is_absolute() else workspace_root / raw_output
    logger.info(f"Output: {output_path}")

    try:
        input_path = resolve_input_path(options.data)
        if not input_path.exists():
            logger.error(f"Input path does not exist: {input_path}")
            sys.exit(1)

        # Collect files
        extensions = options.ext or (["c"] if options.mode == "cpg" else ["json"])
        predicate = lambda p: any(p.endswith(f".{ext}") for ext in extensions)

        files = collect_files_recursively(input_path, predicate, None, None)

        if not files:
            logger.error(f"No files found matching extensions: {extensions}")
            sys.exit(1)

        logger.info(f"Found {len(files)} file(s) to process")

        # Process files
        output_path.mkdir(parents=True, exist_ok=True)

        workers = int(options.workers) if options.workers else 4

        if options.mode == "cpg":
            # Use multiprocess batch generation for CPG mode
            username = os.getenv("USER") or os.getenv("USERNAME") or "user"
            container_name = f"ssat-joern-{username}"

            completed = 0
            logger.start_progress(len(files))

            def on_progress(result):
                nonlocal completed
                completed += 1
                if not result["success"]:
                    logger.error(f"Error processing {result['file']}: {result.get('error', 'Unknown')}")
                logger.update_progress(completed)

            results = batch_generate_cpg(
                files=files,
                input_root=input_path,
                output_root=output_path,
                container_name=container_name,
                workers=workers,
                representation=options.representation,
                export_format=options.export_format,
                copy_source=options.copy_source,
                progress_callback=on_progress,
            )

            logger.stop_progress()

            success_count = sum(1 for r in results if r["success"])
            fail_count = len(results) - success_count
            logger.info(f"Batch complete: {success_count} succeeded, {fail_count} failed")
        elif workers == 1:
            # Sequential processing
            logger.start_progress(len(files))
            for i, file_path in enumerate(files):
                await process_single_file(file_path, input_path, output_path, options, logger)
                logger.update_progress(i + 1)
            logger.stop_progress()
        else:
            # Parallel processing (simplified - would need proper async queue)
            logger.start_progress(len(files))
            tasks = [process_single_file(f, input_path, output_path, options, logger) for f in files]
            await asyncio.gather(*tasks)
            logger.stop_progress()

        logger.info(f"Processing complete. Results written to: {output_path}")

    except KeyboardInterrupt:
        logger.error("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if options.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def ssat_main() -> None:
    """Synchronous entry point for SSAT CLI."""
    asyncio.run(main())


def cpg_main() -> None:
    """Shortcut entry point for CPG generation."""
    sys.argv.insert(1, "cpg")
    # Handle positional argument if present
    if len(sys.argv) > 2 and not sys.argv[2].startswith("-"):
        val = sys.argv.pop(2)
        sys.argv.insert(2, "--data")
        sys.argv.insert(3, val)
    ssat_main()


def generate_cpg_entry() -> None:
    """Entry point for generate:cpg."""
    sys.argv.insert(1, "cpg")
    ssat_main()


def generate_template_entry() -> None:
    """Entry point for generate:template."""
    sys.argv.insert(1, "template")
    ssat_main()


def generate_template_functions_entry() -> None:
    """Entry point for generate:template:functions."""
    sys.argv.insert(1, "template-functions")
    ssat_main()


def generate_dfg_entry() -> None:
    """Entry point for generate:dfg."""
    sys.argv.insert(1, "dfg")
    ssat_main()


def generate_ast_entry() -> None:
    """Entry point for generate:ast."""
    sys.argv.insert(1, "ast")
    ssat_main()


def generate_full_entry() -> None:
    """Entry point for generate:full."""
    sys.argv.insert(1, "full")
    ssat_main()


def scripts_help() -> None:
    """Python equivalent of scripts:help from package.json."""
    try:
        import tomllib
    except ImportError:
        # Fallback for Python < 3.11 if needed, though we use 3.14
        import pip._vendor.tomli as tomllib  # type: ignore

    repo_root = find_monorepo_root(Path.cwd())
    pyproject_path = repo_root / "pyproject.toml"

    if not pyproject_path.exists():
        print("pyproject.toml not found.")
        return

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    scripts = data.get("tool", {}).get("uv", {}).get("scripts", {})
    if not scripts:
        scripts = data.get("project", {}).get("scripts", {})

    print("Available scripts\n==================")
    for k, v in sorted(scripts.items()):
        print(f"{k:30} - {v}")


def docker_up() -> None:
    """Start Docker services."""
    import subprocess
    import os
    try:
        os.makedirs("workspace", exist_ok=True)
        os.chmod("workspace", 0o777)
        subprocess.run(["docker", "compose", "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error starting Docker services: {e}")
        sys.exit(1)


def docker_down() -> None:
    """Stop Docker services and remove volumes."""
    import subprocess
    try:
        subprocess.run(["docker", "compose", "down", "-v"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error stopping Docker services: {e}")
        sys.exit(1)


def docker_remove() -> None:
    """Alias for docker_down."""
    docker_down()


def docker_fresh() -> None:
    """Fresh restart of Docker services (rebuild without cache)."""
    import subprocess
    import os
    try:
        print("Cleaning up existing containers, volumes, and local images...")
        subprocess.run(["docker", "compose", "down", "-v", "--rmi", "local"], check=True)
        print("Rebuilding and starting services from scratch...")
        os.makedirs("workspace", exist_ok=True)
        os.chmod("workspace", 0o777)
        subprocess.run(["docker", "compose", "up", "-d", "--build", "--no-cache"], check=True)
        print("Fresh start complete.")
    except subprocess.CalledProcessError as e:
        print(f"Error during fresh restart: {e}")
        sys.exit(1)


def type_check_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["mypy", "packages"]).returncode)


def lint_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["ruff", "check", "packages"]).returncode)


def lint_fix_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["ruff", "check", "--fix", "packages"]).returncode)


def format_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["ruff", "format", "packages"]).returncode)


def format_check_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["ruff", "format", "--check", "packages"]).returncode)


def test_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["pytest", "packages/core"]).returncode)


def test_log_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["pytest", "-s", "packages/core"]).returncode)


def web_dev_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["bash", "-c", "cd web && npm run dev"]).returncode)


def web_build_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["bash", "-c", "cd web && npm run build"]).returncode)


def web_start_entry() -> None:
    import subprocess
    sys.exit(subprocess.run(["bash", "-c", "cd web && npm run start"]).returncode)


if __name__ == "__main__":
    ssat_main()
