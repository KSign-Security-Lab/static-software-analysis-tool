"""Main entry point for SSAT CLI."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, cast

from .logger import SimpleLogger
from .parser import CliOptions, CliParser

from ssat.cpg.generator import SUPPORTED_EXTENSIONS, batch_generate_cpg
from ssat.types.cpg import CPGRoot
from ssat.pipeline import (
    analyze_cpg,
    generate_ast,
    generate_cpg_from_file,
    generate_dfg,
    generate_template,
    training_record,
)


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


def collect_files_recursively(root_path: Path, predicate: Callable[[str], bool]) -> List[Path]:
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
    for sep in [
        "_",
        "(",
        ")",
        "[",
        "]",
        "{",
        "}",
        ":",
        ";",
        ",",
        ".",
        "?",
        "!",
        "|",
        "&",
        "^",
        "~",
        "`",
        "'",
        '"',
        " ",
        "\n",
        "\t",
        "\r",
        "\b",
        "\f",
    ]:
        m = m.split(sep)[-1]
    return sanitize_token(m) if m else fallback


def process_single_file(
    file_path: Path,
    input_root: Path,
    output_root: Path,
    options: CliOptions,
    logger: SimpleLogger,
) -> None:
    """Process a single file."""
    is_source_file = file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    cpg: CPGRoot

    try:
        if is_source_file:
            cpg = generate_cpg_from_file(
                file_path,
                backend=options.backend,
                representation=options.representation,
            )
        else:
            # Assume JSON file with CPG data
            # A CPG JSON file on disk: json.loads gives Any, so state the shape once.
            cpg = cast(CPGRoot, json.loads(file_path.read_text(encoding="utf-8")))

        result: Any = None

        if options.mode == "cpg":
            result = cpg
        elif options.mode == "template":
            result = generate_template(cpg)
        elif options.mode == "ast":
            result = generate_ast(generate_template(cpg))
        elif options.mode == "dfg":
            result = generate_dfg(generate_template(cpg))
        elif options.mode == "full":
            # One pass: AST and DFG for each function, in the schema the GNN reads.
            result = [
                training_record(fn, include_template=False, include_label=True)
                for fn in analyze_cpg(cpg, source=str(file_path))
            ]
        elif options.mode == "template-functions":
            from ssat.utils import get_functions_from_template

            template = generate_template(cpg)
            result = get_functions_from_template(template)
        elif options.mode == "f2a":
            # F2-A consumes a CPG directly (see ssat.f2a).
            from ssat.f2a import run_f2a

            f2a_result = run_f2a(cpg, source_cpg=str(file_path))
            result = f2a_result.model_dump()

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
                        debug_code = nodes[0].get("debug", {}).get("code") if nodes else None
                        fn_name = extract_name_from_code(debug_code, f"func_{i}")
                        per_func_file = out_dir / f"{base}_{fn_name}_{options.mode}.json"
                        per_func_file.write_text(json.dumps(dfg, indent=2), encoding="utf-8")
                elif options.mode == "full":
                    # Each record already carries the top-level `ast`/`dfg` keys
                    # agent.dataset.JsonDataset reads. The previous shape
                    # (`ast_result`/`dfg_result`) was unreadable by the trainer.
                    for idx, record in enumerate(result if isinstance(result, list) else []):
                        func_name = sanitize_token(record.get("function_name") or f"func_{idx}")
                        per_func_file = out_dir / f"{base}_{func_name}_{options.mode}.json"
                        per_func_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
            else:
                # Single file output for other modes
                output_file = out_dir / f"{base}_{options.mode}.json"
                output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        if options.debug:
            import traceback

            traceback.print_exc()


def main() -> None:
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

        def predicate(p: str) -> bool:
            return any(p.endswith(f".{ext}") for ext in extensions)

        files = collect_files_recursively(input_path, predicate)

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

            def on_progress(result: Dict[str, Any]) -> None:
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
        else:
            # Analysis after CPG generation is CPU-bound Python. --workers
            # parallelises the CPG batch path above (a real process pool); the
            # previous "parallel" branch here gathered coroutines that never
            # awaited anything, so it ran sequentially while looking concurrent.
            logger.start_progress(len(files))
            for i, file_path in enumerate(files):
                process_single_file(file_path, input_path, output_path, options, logger)
                logger.update_progress(i + 1)
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
    """Entry point for the SSAT CLI."""
    main()


if __name__ == "__main__":
    ssat_main()
