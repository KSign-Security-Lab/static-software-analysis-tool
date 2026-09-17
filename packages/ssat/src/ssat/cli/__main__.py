import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast

from .logger import SimpleLogger
from .parser import CliOptions, CliParser

from ssat.cpg.backends import EmbeddedBackend
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
    current = start_dir
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


def resolve_input_path(data_path: str) -> Path:
    path = Path(data_path)
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    repo_root = find_monorepo_root(Path.cwd())
    repo_path = repo_root / data_path
    if repo_path.exists():
        return repo_path.resolve()
    return path.resolve()


def collect_files_recursively(root_path: Path, predicate: Callable[[str], bool]) -> List[Path]:
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
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in s)[:100]


def extract_name_from_code(code: str | None, fallback: str) -> str:
    if not code:
        return fallback
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


def load_cpg_file(file_path: Path) -> CPGRoot:
    """`ssat cpg` writes bare GraphSON; the later stages take it under an `export` key."""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "export" in data:
        return cast(CPGRoot, data)
    return CPGRoot(export=cast(Dict[str, Any], data))


def process_single_file(
    file_path: Path,
    input_root: Path,
    output_root: Path,
    options: CliOptions,
    logger: SimpleLogger,
) -> None:
    is_source_file = file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    cpg: CPGRoot

    try:
        if is_source_file:
            cpg = generate_cpg_from_file(
                file_path,
                representation=options.representation,
            )
        else:
            cpg = load_cpg_file(file_path)

        result: Any = None
        macro = options.replace_macro

        if options.mode == "cpg":
            result = cpg
        elif options.mode == "template":
            result = generate_template(cpg, replace_macro=macro)
        elif options.mode == "ast":
            result = generate_ast(generate_template(cpg, replace_macro=macro))
        elif options.mode == "dfg":
            result = generate_dfg(generate_template(cpg, replace_macro=macro))
        elif options.mode == "full":
            result = [
                training_record(fn, include_template=False, include_label=True)
                for fn in analyze_cpg(cpg, source=str(file_path), replace_macro=macro)
            ]
        elif options.mode == "template-functions":
            from ssat.utils import get_functions_from_template

            template = generate_template(cpg, replace_macro=macro)
            result = get_functions_from_template(template)
        elif options.mode == "f2a":
            from ssat.f2a import run_f2a

            f2a_result = run_f2a(cpg, source_cpg=str(file_path))
            result = f2a_result.model_dump()

        if result is not None:
            base = file_path.stem
            relative = file_path.relative_to(input_root) if file_path.is_relative_to(input_root) else file_path
            out_dir = output_root / relative.parent
            out_dir.mkdir(parents=True, exist_ok=True)

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
                    for idx, record in enumerate(result if isinstance(result, list) else []):
                        func_name = sanitize_token(record.get("function_name") or f"func_{idx}")
                        per_func_file = out_dir / f"{base}_{func_name}_{options.mode}.json"
                        per_func_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
            else:
                output_file = out_dir / f"{base}_{options.mode}.json"
                output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        if options.debug:
            import traceback

            traceback.print_exc()


def main(argv: Optional[List[str]] = None) -> None:
    parser = CliParser()
    options = parser.parse(argv)
    logger = SimpleLogger(options.debug)

    if options.debug:
        logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(name)s: %(message)s")

    logger.info("Static Software Analysis Tool (SSAT) v2.4.3")
    logger.info(f"Mode: {options.mode}")
    logger.info(f"Input: {options.data}")

    workspace_root = find_monorepo_root(Path.cwd())
    raw_output = options.output or f"result/{options.mode}_{int(__import__('time').time())}"
    output_path = Path(raw_output) if Path(raw_output).is_absolute() else workspace_root / raw_output
    logger.info(f"Output: {output_path}")

    try:
        input_path = resolve_input_path(options.data)
        if not input_path.exists():
            logger.error(f"Input path does not exist: {input_path}")
            sys.exit(1)

        extensions = options.ext or (["c"] if options.mode == "cpg" else ["json"])

        def predicate(p: str) -> bool:
            return any(p.endswith(f".{ext}") for ext in extensions)

        files = collect_files_recursively(input_path, predicate)

        if not files:
            logger.error(f"No files found matching extensions: {extensions}")
            sys.exit(1)

        logger.info(f"Found {len(files)} file(s) to process")

        if not EmbeddedBackend().is_available():
            from ssat.cpg.embedded import joern_home

            logger.error(
                f"no Joern JARs under {joern_home()}, and Joern runs in this process.\n"
                "  point JOERN_HOME at a joern-cli install:  JOERN_HOME=/path/to/joern-cli ssat ...\n"
                "  a JDK has to be on the path too."
            )
            sys.exit(1)

        output_path.mkdir(parents=True, exist_ok=True)

        workers = int(options.workers) if options.workers else 4

        if options.mode == "cpg":
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
                workers=workers,
                representation=options.representation,
                copy_source=options.copy_source,
                progress_callback=on_progress,
            )

            logger.stop_progress()

            success_count = sum(1 for r in results if r["success"])
            fail_count = len(results) - success_count
            logger.info(f"Batch complete: {success_count} succeeded, {fail_count} failed")
        else:
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
    # No arguments on a terminal: ask, rather than print a usage error.
    if len(sys.argv) == 1 and sys.stdin.isatty():
        from .interactive import run_interactive

        sys.exit(run_interactive(main))
    main()


if __name__ == "__main__":
    ssat_main()
