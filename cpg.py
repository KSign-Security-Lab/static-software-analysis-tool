#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm


def run_joern_pipeline(input_file, output_root, representation, export_format, copy_source=True):
    """
    Runs joern-parse and joern-export for a single file.
    """
    input_path = Path(input_file).resolve()

    # Create the mirrored output directory path
    try:
        rel_path = input_path.relative_to(Path.cwd())
    except ValueError:
        rel_path = Path(input_path.name)

    # Output directory per file
    output_dir = Path(output_root) / rel_path
    
    # Joern export requires the directory to NOT exist
    if output_dir.exists():
        shutil.rmtree(output_dir)
    
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp_cpg:
        tmp_cpg_path = tmp_cpg.name

    try:
        # 1. Joern Parse
        parse_cmd = ["joern-parse", str(input_path), "--output", tmp_cpg_path]
        subprocess.run(parse_cmd, check=True, capture_output=True, text=True)

        # 2. Joern Export
        # Note: 'repr=all' produces 'export.json' for 'graphson' format
        export_cmd = [
            "joern-export",
            "--repr", representation,
            "--format", export_format,
            "--out", str(output_dir),
            tmp_cpg_path,
        ]
        subprocess.run(export_cmd, check=True, capture_output=True, text=True)

        # 3. Rename export.json to original_filename.json if it exists
        export_file = output_dir / "export.json"
        if export_file.exists():
            new_name = output_dir / f"{input_path.stem}.json"
            export_file.rename(new_name)
        
        # 4. Copy source code side-by-side
        if copy_source:
            shutil.copy2(input_path, output_dir / input_path.name)

        return True, str(input_path), None
    except subprocess.CalledProcessError as e:
        return False, str(input_path), f"STDOUT: {e.stdout}\nSTDERR: {e.stderr}"
    except Exception as e:
        return False, str(input_path), str(e)
    finally:
        if os.path.exists(tmp_cpg_path):
            os.remove(tmp_cpg_path)


def main():
    parser = argparse.ArgumentParser(description="Parallel Joern Parse and Export")
    parser.add_argument("input", help="Input directory or file")
    parser.add_argument(
        "-o", "--output", default="cpg_export", help="Output root directory"
    )
    parser.add_argument(
        "-r", "--repr", default="all", help="Representation (ast, cfg, cpg14, all, etc.)"
    )
    parser.add_argument(
        "-f",
        "--format",
        default="graphson",
        help="Export format (dot, graphson, graphml, etc.)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=min(os.cpu_count() or 1, 8),
        help="Number of parallel jobs (default: min(CPU_COUNT, 8))",
    )
    parser.add_argument(
        "-e",
        "--extensions",
        nargs="+",
        default=[".c", ".cpp", ".h", ".java", ".py", ".js"],
        help="File extensions to process (default: .c .cpp .h .java .py .js)",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Do not copy source code side-by-side",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    files_to_process = []

    if input_path.is_file():
        files_to_process.append(input_path)
    elif input_path.is_dir():
        for ext in args.extensions:
            files_to_process.extend(input_path.rglob(f"*{ext}"))
    else:
        print(f"Error: {args.input} is not a valid file or directory")
        return

    if not files_to_process:
        print("No files found to process.")
        return

    print(
        f"Found {len(files_to_process)} files. Processing with {args.jobs} parallel jobs..."
    )

    results = []
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(
                run_joern_pipeline, f, args.output, args.repr, args.format, not args.no_copy
            ): f
            for f in files_to_process
        }

        for future in tqdm(as_completed(futures), total=len(futures)):
            results.append(future.result())

    # Summary
    successes = [r for r in results if r[0]]
    failures = [r for r in results if not r[0]]

    print(f"\nProcessing complete!")
    print(f"Success: {len(successes)}")
    print(f"Failure: {len(failures)}")

    if failures:
        print("\nFailures:")
        for _, path, error in failures:
            print(f"- {path}: {error}")


if __name__ == "__main__":
    main()
