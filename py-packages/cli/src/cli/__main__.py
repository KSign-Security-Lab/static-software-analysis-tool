"""Main entry point for SSAT CLI."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .logger import SimpleLogger
from .parser import CliOptions, CliParser

# Import core functions
try:
    from core.endpoint import generate_ast, generate_cpg, generate_dfg, generate_template
except ImportError:
    # Fallback if core is not installed
    def generate_cpg(*args, **kwargs):
        raise NotImplementedError("Core package not available")

    def generate_template(*args, **kwargs):
        raise NotImplementedError("Core package not available")

    def generate_ast(*args, **kwargs):
        raise NotImplementedError("Core package not available")

    def generate_dfg(*args, **kwargs):
        raise NotImplementedError("Core package not available")


def find_monorepo_root(start_dir: Path) -> Path:
    """Find monorepo root by looking for package.json."""
    current = start_dir
    while current != current.parent:
        if (current / "package.json").exists():
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
    is_c_file = file_path.suffix.lower() == ".c"
    cpg = None

    try:
        if is_c_file:
            cpg = await generate_cpg(str(file_path), "file")
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
            from core.ast.utils import recursively_get_functions_from_template
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

        workers = int(options.workers) if options.workers else 1
        if workers == 1 or options.mode == "cpg":
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


if __name__ == "__main__":
    asyncio.run(main())


