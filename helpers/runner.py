import argparse
import json
import multiprocessing
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from tqdm import tqdm  # Always require tqdm


# ---------------------------
# Macro replacement (C/C++)
# ---------------------------
def replace_macros(src_root: str, macro_exts=(".c", ".h")):
    """
    Scan C/C++ headers/sources for #define macros and replace occurrences with their definitions.
    Writes results to sibling files with '_macro_replaced' suffix (same extension).
    """
    src_root = os.path.abspath(src_root)
    macros = {}
    define_lines = {}

    print(f"Scanning for macro definitions in {src_root} ...", file=sys.stderr)

    # First pass: collect macro definitions
    for root, _, files in os.walk(src_root):
        # Check for macro replaced files and skip both original and replaced from further processing
        # Collect base names of files that have already been macro replaced
        macro_replaced_bases = set()
        for fname in files:
            if "_macro_replaced." in fname:
                base = fname.replace("_macro_replaced", "")
                macro_replaced_bases.add(base)

        # Filter out both the original and macro replaced files from files list
        files[:] = [
            fname
            for fname in files
            if not (
                fname in macro_replaced_bases
                or fname.replace("_macro_replaced", "") in macro_replaced_bases
            )
        ]

        print(f"Found {len(files)} files to process.", file=sys.stderr)

        for fname in files:
            if any(fname.lower().endswith(ext) for ext in macro_exts):
                path = os.path.join(root, fname)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    define_lines[path] = []
                    for idx, line in enumerate(lines):
                        m = re.match(r"^\s*#define\s+(\w+)\s+(.+)", line)
                        if m:
                            name, val = m.groups()
                            macros[name] = val.strip()
                            define_lines[path].append(idx)
                except Exception as e:
                    print(
                        f"[WARN] Skipping macro scan for {path}: {e}", file=sys.stderr
                    )
    if not macros:
        print("No macros found for replacement.", file=sys.stderr)
        return

    # Second pass: replace macros and write to _macro_replaced.*
    for root, _, files in os.walk(src_root):
        for fname in files:
            if any(fname.lower().endswith(ext) for ext in macro_exts):
                path = os.path.join(root, fname)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()

                    updated_lines = []
                    for idx, line in enumerate(lines):
                        if idx in define_lines.get(path, []):
                            continue  # drop original #define lines
                        # naive whole-word macro replacement
                        for name, val in macros.items():
                            pattern = r"\b" + re.escape(name) + r"\b"
                            line = re.sub(pattern, val, line)
                        updated_lines.append(line)

                    base, ext = os.path.splitext(fname)
                    new_fname = base + "_macro_replaced" + ext
                    new_path = os.path.join(root, new_fname)
                    with open(new_path, "w", encoding="utf-8") as f:
                        f.writelines(updated_lines)
                except Exception as e:
                    print(
                        f"[WARN] Failed to replace macros in {path}: {e}",
                        file=sys.stderr,
                    )


# ---------------------------
# File discovery
# ---------------------------
def gather_source_files(src_root: str, exts):
    src_root = os.path.abspath(src_root)
    p = Path(src_root)
    if p.is_file():
        return [str(p)]
    src_files = []
    for root, _, files in os.walk(src_root):
        for fname in files:
            if exts:
                if any(fname.lower().endswith(ext.lower()) for ext in exts):
                    src_files.append(os.path.join(root, fname))
            else:
                src_files.append(os.path.join(root, fname))
    return src_files


def process_file_cpg(task):
    src_file, src_root, out_root = task
    rel_path = os.path.relpath(src_file, src_root)
    base, _ext = os.path.splitext(rel_path)

    # When src_root == parent dir of a single file, rel_path can be just the filename.
    # If anything collapses to "." or "", fall back to the basename.
    if base in (".", ""):
        base = os.path.splitext(os.path.basename(src_file))[0]

    out_rel_path = base + ".json"
    out_file = os.path.join(out_root, out_rel_path)

    try:
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
    except Exception as e:
        return (src_file, False, f"Failed to create output dir: {e}")

    with tempfile.TemporaryDirectory() as tmpdir:
        # joern-parse
        parse_cmd = ["joern-parse", src_file]
        proc_parse = subprocess.run(
            parse_cmd,
            cwd=tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc_parse.returncode != 0:
            msg = proc_parse.stderr.strip() or "joern-parse returned non-zero exit"
            return (src_file, False, f"joern-parse failed: {msg}")

        cpg_path = os.path.join(tmpdir, "cpg.bin")
        if not os.path.isfile(cpg_path):
            return (src_file, False, "cpg.bin not found after joern-parse")

        # joern-export
        export_cmd = ["joern-export", "--repr=all", "--format=graphson"]
        proc_export = subprocess.run(
            export_cmd,
            cwd=tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc_export.returncode != 0:
            msg = proc_export.stderr.strip() or "joern-export returned non-zero exit"
            return (src_file, False, f"joern-export failed: {msg}")

        out_dir = os.path.join(tmpdir, "out")
        if not os.path.isdir(out_dir):
            # Some joern versions can emit JSON to stdout
            graphson_output = proc_export.stdout
            if graphson_output and graphson_output.strip().startswith("{"):
                try:
                    parsed = json.loads(graphson_output)
                    with open(out_file, "w", encoding="utf-8") as f:
                        json.dump(parsed, f)
                    return (src_file, True, "OK (stdout JSON)")
                except Exception as e:
                    return (src_file, False, f"Invalid JSON from stdout: {e}")
            return (
                src_file,
                False,
                "joern-export produced no 'out' dir nor JSON on stdout",
            )

        # Merge all JSON in out/
        merged = {}
        for entry in os.listdir(out_dir):
            path = os.path.join(out_dir, entry)
            if os.path.isfile(path) and entry.lower().endswith(".json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    return (src_file, False, f"Failed to load JSON from {entry}: {e}")
                name, _ = os.path.splitext(entry)
                merged[name] = data

        if not merged:
            return (
                src_file,
                False,
                "No JSON files found in joern-export output directory",
            )

        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(merged, f)
        except Exception as e:
            return (src_file, False, f"Failed writing merged JSON: {e}")

    return (src_file, True, "OK")


def process_file_kast(task):
    src_file, src_root, out_root = task
    rel_path = os.path.relpath(src_file, src_root)
    base_no_ext, ext = os.path.splitext(rel_path)

    if base_no_ext in (".", ""):
        base_no_ext = os.path.splitext(os.path.basename(src_file))[0]

    if ext.lower() != ".json":
        return (src_file, False, "kast expects .json CPG inputs")

    # Put outputs for this file under out_root/<rel/path/without_ext>/
    out_dir = os.path.join(out_root, base_no_ext)

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return (src_file, False, f"Failed to create output dir: {e}")

    # Run exactly as your working manual call
    cmd = ["npx", "tsx", "src/script/generateAST.ts", src_file, out_dir]
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    if proc.returncode != 0:
        msg = proc.stderr.strip() or "kast command returned non-zero exit"
        return (src_file, False, f"kast failed: {msg}")

    # Validate the four expected outputs
    name = os.path.basename(base_no_ext)  # file name without extension
    expected = [
        os.path.join(out_dir, f"{name}_astTree.json"),
        os.path.join(out_dir, f"{name}_templateTree.json"),
        os.path.join(out_dir, f"{name}_text.txt"),
        os.path.join(out_dir, f"{name}_flatten.json"),
    ]
    missing = [p for p in expected if not os.path.isfile(p)]
    if missing:
        return (
            src_file,
            False,
            f"kast missing expected outputs: {', '.join(os.path.basename(m) for m in missing)}",
        )

    return (src_file, True, "OK")


# ---------------------------
# Orchestration
# ---------------------------
def run_tasks(mode, src_files, src_root, out_root, workers):
    total = len(src_files)
    print(f"Found {total} files to process.", file=sys.stderr)
    if total == 0:
        print("No files found. Exiting.", file=sys.stderr)
        return

    if mode == "cpg":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_cpg
    else:  # "kast"
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_kast

    successes = 0
    failures = []

    print(
        f"Processing {total} files with {workers} workers in '{mode}' mode ...",
        file=sys.stderr,
    )
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_file = {executor.submit(worker, task): task[0] for task in tasks}
        pbar = tqdm(total=total, desc="Files processed", unit="file")
        for future in as_completed(future_to_file):
            src_file = future_to_file[future]
            try:
                file_path, ok, msg = future.result()
            except Exception as e:
                failures.append((src_file, f"Exception: {e}"))
                print(
                    f"[ERROR] Unexpected exception for {src_file}: {e}", file=sys.stderr
                )
            else:
                if ok:
                    successes += 1
                else:
                    failures.append((file_path, msg))
                    print(f"[FAIL] {file_path}: {msg}", file=sys.stderr)
            pbar.update(1)
        pbar.close()

    print(f"Done. Successes: {successes}, Failures: {len(failures)}", file=sys.stderr)
    if failures:
        print("Failures detailed below:", file=sys.stderr)
        for fpath, reason in failures:
            print(f"  {fpath}: {reason}", file=sys.stderr)
    else:
        print("All files processed successfully.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Batch processor: 'cpg' (joern-parse/export) or 'kast' (tsx AST generator)."
    )
    parser.add_argument(
        "--mode", required=True, choices=["cpg", "kast"], help="Run mode: cpg or kast."
    )
    parser.add_argument(
        "--data", required=True, help="Path to source file or directory."
    )
    parser.add_argument("--save", help="Output directory for results (root).")
    parser.add_argument(
        "--ext",
        nargs="*",
        help="File extensions to include. Provide no args (i.e., --ext) to include all files.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=(multiprocessing.cpu_count() or 1),
        help="Number of parallel workers. Defaults to CPU count.",
    )
    parser.add_argument(
        "--replace-macro",
        action="store_true",
        default=True,
        help="Scan and replace #define macros in C/C++ code before processing.",
    )
    args = parser.parse_args()

    data_path = Path(args.data).resolve()

    if args.save:
        out_root = os.path.abspath(args.save)
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_root = os.path.abspath(os.path.join("result", ts, args.mode))

    # Determine root-for-relpath and the actual file list to process
    if data_path.is_file():
        src_root_dir = str(data_path.parent)  # root for relpath
        input_is_file = True
    else:
        src_root_dir = str(data_path)  # root directory
        input_is_file = False

    print(f"Scanning for source files under {src_root_dir} ...", file=sys.stderr)
    default_exts = (
        [".c", ".cpp"] if args.mode == "cpg" else [".json"]  # kast: ONLY json inputs
    )
    exts = args.ext if args.ext is not None else default_exts

    # Optional macro replacement (only meaningful for C/C++ sources)
    if args.replace_macro:
        replace_macros(src_root_dir, default_exts)

    if input_is_file:
        src_files = [str(data_path)]
    else:
        src_files = gather_source_files(src_root_dir, exts)

    if not src_files:
        print("No files found. Exiting.", file=sys.stderr)
        return

    run_tasks(
        mode=args.mode,
        src_files=src_files,
        src_root=src_root_dir,  # IMPORTANT: pass the DIRECTORY as the relpath root
        out_root=out_root,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
