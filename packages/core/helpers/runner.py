import argparse
import json
import multiprocessing
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, Optional, Tuple

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
# Joern Server Pool Management
# ---------------------------
class JoernServerManager:
    """
    Manages a pool of persistent Joern server instances to reduce startup overhead.
    Each server runs in its own thread and processes CPG generation requests.
    """

    def __init__(self, num_servers: int, server_timeout: int = 30):
        self.num_servers = num_servers
        self.server_timeout = server_timeout
        self.servers = []
        self.server_queues = []
        self.server_threads = []
        self.shutdown_event = threading.Event()
        self.lock = threading.Lock()

    def start_servers(self):
        """Start all Joern server instances in separate threads."""
        print(f"Starting {self.num_servers} Joern server instances...", file=sys.stderr)

        for i in range(self.num_servers):
            # Create a queue for this server's requests
            server_queue = Queue()
            self.server_queues.append(server_queue)

            # Start server thread
            server_thread = threading.Thread(
                target=self._server_worker, args=(i, server_queue), daemon=True
            )
            server_thread.start()
            self.server_threads.append(server_thread)

        # Wait a moment for servers to initialize
        time.sleep(2)
        print(f"Started {self.num_servers} Joern server instances", file=sys.stderr)

    def _server_worker(self, server_id: int, request_queue: Queue):
        """Worker thread that runs a persistent Joern server."""
        server_process = None
        server_dir = None

        try:
            while not self.shutdown_event.is_set():
                src_file = None
                result_queue = None
                try:
                    # Wait for a request with timeout
                    request = request_queue.get(timeout=1.0)
                    if request is None:  # Shutdown signal
                        break

                    src_file, result_queue = request

                    # Process the file
                    result = self._process_file_with_server(src_file, server_id)
                    result_queue.put(result)

                except Empty:
                    continue
                except Exception as e:
                    # Try to send error result if we have the necessary variables
                    if result_queue is not None and src_file is not None:
                        try:
                            result_queue.put((src_file, False, f"Server error: {e}"))
                        except:
                            pass  # Ignore errors in error handling
                    print(f"[ERROR] Server {server_id} error: {e}", file=sys.stderr)

        finally:
            # Cleanup server process
            if server_process and server_process.poll() is None:
                server_process.terminate()
                try:
                    server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server_process.kill()
            if server_dir and os.path.exists(server_dir):
                import shutil

                shutil.rmtree(server_dir, ignore_errors=True)

    def _process_file_with_server(
        self, src_file: str, server_id: int
    ) -> Tuple[str, bool, Any]:
        """Process a single file using a dedicated server instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
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
                    msg = (
                        proc_parse.stderr.strip()
                        or "joern-parse returned non-zero exit"
                    )
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
                    msg = (
                        proc_export.stderr.strip()
                        or "joern-export returned non-zero exit"
                    )
                    return (src_file, False, f"joern-export failed: {msg}")

                out_dir = os.path.join(tmpdir, "out")
                if not os.path.isdir(out_dir):
                    # Some joern versions can emit JSON to stdout
                    graphson_output = proc_export.stdout
                    if graphson_output and graphson_output.strip().startswith("{"):
                        try:
                            parsed = json.loads(graphson_output)
                            return (src_file, True, parsed)
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
                            return (
                                src_file,
                                False,
                                f"Failed to load JSON from {entry}: {e}",
                            )
                        name, _ = os.path.splitext(entry)
                        merged[name] = data

                if not merged:
                    return (
                        src_file,
                        False,
                        "No JSON files found in joern-export output directory",
                    )

                return (src_file, True, merged)

            except Exception as e:
                return (src_file, False, f"Processing error: {e}")

    def submit_request(self, src_file: str) -> Tuple[str, bool, Any]:
        """Submit a CPG generation request to an available server."""
        # Simple round-robin load balancing
        with self.lock:
            server_id = len(self.servers) % self.num_servers
            self.servers.append(server_id)

        result_queue = Queue()
        request = (src_file, result_queue)

        # Submit to the selected server
        self.server_queues[server_id].put(request)

        # Wait for result
        try:
            result = result_queue.get(timeout=self.server_timeout)
            return result
        except Empty:
            return (src_file, False, "Server timeout")

    def shutdown(self):
        """Shutdown all server instances."""
        print("Shutting down Joern servers...", file=sys.stderr)
        self.shutdown_event.set()

        # Send shutdown signals to all servers
        for queue in self.server_queues:
            queue.put(None)

        # Wait for all threads to finish
        for thread in self.server_threads:
            thread.join(timeout=5)

        print("Joern servers shutdown complete", file=sys.stderr)


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


def process_file_cpg(task: Tuple[str, str, str, JoernServerManager]):
    """Process a single file for CPG generation using the server pool."""
    src_file, src_root, out_root, server_manager = task
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

    # Submit request to server pool
    file_path, success, result = server_manager.submit_request(src_file)

    if not success:
        return (file_path, False, result)

    # Write the result to output file
    try:
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f)
        return (file_path, True, "OK")
    except Exception as e:
        return (file_path, False, f"Failed writing JSON: {e}")


def process_file_cpg_legacy(task):
    """Legacy CPG processing function (kept for fallback)."""
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


def process_file_template(task):
    src_file, src_root, out_root = task
    rel_path = os.path.relpath(src_file, src_root)
    base_no_ext, ext = os.path.splitext(rel_path)

    if base_no_ext in (".", ""):
        base_no_ext = os.path.splitext(os.path.basename(src_file))[0]

    if ext.lower() != ".json":
        return (src_file, False, "template expects .json CPG inputs")

    # Create output directory preserving relative path structure but without filename subdirectory
    # Extract relative path from src_file and create corresponding output structure
    rel_path = os.path.relpath(src_file, src_root)
    rel_dir = os.path.dirname(rel_path)

    if rel_dir and rel_dir != ".":
        out_dir = os.path.join(out_root, rel_dir)
    else:
        out_dir = out_root

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return (src_file, False, f"Failed to create output dir: {e}")

    # Run exactly as your working manual call
    cmd = ["npx", "tsx", "script/generateTemplate.ts", src_file, out_dir]
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    if proc.returncode != 0:
        msg = proc.stderr.strip() or "template command returned non-zero exit"
        return (src_file, False, f"template failed: {msg}")

    name = os.path.basename(base_no_ext)  # file name without extension
    expected = [
        os.path.join(out_dir, f"{name}_templateTree.json"),
    ]
    missing = [p for p in expected if not os.path.isfile(p)]
    if missing:
        return (
            src_file,
            False,
            f"template missing expected outputs: {', '.join(os.path.basename(m) for m in missing)}",
        )

    return (src_file, True, "OK")


def process_file_dfg(task):
    src_file, src_root, out_root = task
    rel_path = os.path.relpath(src_file, src_root)
    base_no_ext, ext = os.path.splitext(rel_path)

    if base_no_ext in (".", ""):
        base_no_ext = os.path.splitext(os.path.basename(src_file))[0]

    if ext.lower() != ".json":
        return (src_file, False, "dfg expects .json CPG inputs")

    # Create output directory preserving relative path structure but without filename subdirectory
    # Extract relative path from src_file and create corresponding output structure
    rel_path = os.path.relpath(src_file, src_root)
    rel_dir = os.path.dirname(rel_path)

    if rel_dir and rel_dir != ".":
        out_dir = os.path.join(out_root, rel_dir)
    else:
        out_dir = out_root

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return (src_file, False, f"Failed to create output dir: {e}")

    # Run exactly as your working manual call
    cmd = ["npx", "tsx", "script/generateDFG.ts", src_file, out_dir]
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    if proc.returncode != 0:
        msg = proc.stderr.strip() or "dfg command returned non-zero exit"
        return (src_file, False, f"dfg failed: {msg}")

    name = os.path.basename(base_no_ext)  # file name without extension
    expected = [
        os.path.join(out_dir, f"{name}_dfg.json"),
    ]
    missing = [p for p in expected if not os.path.isfile(p)]
    if missing:
        return (
            src_file,
            False,
            f"dfg missing expected outputs: {', '.join(os.path.basename(m) for m in missing)}",
        )

    return (src_file, True, "OK")


def process_file_ast(task):
    """Process a single file for AST extraction using ASTExtractor."""
    src_file, src_root, out_root = task
    rel_path = os.path.relpath(src_file, src_root)
    base_no_ext, ext = os.path.splitext(rel_path)

    if base_no_ext in (".", ""):
        base_no_ext = os.path.splitext(os.path.basename(src_file))[0]

    if ext.lower() != ".json":
        return (src_file, False, "ast expects .json template inputs")

    # Create output directory preserving relative path structure but without filename subdirectory
    # Extract relative path from src_file and create corresponding output structure
    rel_path = os.path.relpath(src_file, src_root)
    rel_dir = os.path.dirname(rel_path)

    if rel_dir and rel_dir != ".":
        out_dir = os.path.join(out_root, rel_dir)
    else:
        out_dir = out_root

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return (src_file, False, f"Failed to create output dir: {e}")

    # Import ASTExtractor
    try:
        ast_extractor_path = os.path.join(os.path.dirname(__file__), "..", "ast")
        sys.path.insert(0, ast_extractor_path)
        from ASTExtractor import (  # pyright: ignore[reportMissingImports]
            ASTExtractorV1_12,
        )
    except ImportError as e:
        return (src_file, False, f"Failed to import ASTExtractor: {e}")

    # Read the template JSON file
    try:
        with open(src_file, "r", encoding="utf-8") as f:
            template_data = json.load(f)
    except Exception as e:
        return (src_file, False, f"Failed to read template file: {e}")

    # Process each function in the template data
    try:
        results = []

        # Handle both single function and array of functions
        full_template = (
            template_data if isinstance(template_data, list) else [template_data]
        )

        # Recursively find all FunctionDefinition nodes
        def find_function_definitions(nodes):
            """Recursively find all FunctionDefinition nodes in the AST tree."""
            functions = []
            if isinstance(nodes, dict):
                if nodes.get("nodeType") == "FunctionDefinition":
                    functions.append(nodes)
                # Search in children
                for child in nodes.get("children", []):
                    functions.extend(find_function_definitions(child))
            elif isinstance(nodes, list):
                for node in nodes:
                    functions.extend(find_function_definitions(node))
            return functions

        functions = find_function_definitions(full_template)

        for func_data in functions:
            if not isinstance(func_data, dict):
                continue

            # Extract function name
            func_name = func_data.get("name", "unknown")

            # Create AST extractor and run
            extractor = ASTExtractorV1_12(func_data, lift_pure_cond_calls=False)
            ast_result = extractor.run()

            # Add function name to result
            ast_result["function_name"] = func_name
            results.append(ast_result)

        # Write the result
        name = os.path.basename(base_no_ext)  # file name without extension
        output_file = os.path.join(out_dir, f"{name}_ast.json")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return (src_file, True, "OK")

    except Exception as e:
        return (src_file, False, f"AST extraction failed: {e}")


# ---------------------------
# Orchestration
# ---------------------------
def run_tasks(mode, src_files, src_root, out_root, workers, server_mode=False):
    total = len(src_files)
    print(f"Found {total} files to process.", file=sys.stderr)
    if total == 0:
        print("No files found. Exiting.", file=sys.stderr)
        return

    if mode == "cpg":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_cpg
    elif mode == "template":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_template
    elif mode == "dfg":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_dfg
    elif mode == "ast":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_ast
    else:
        raise ValueError(f"Invalid mode: {mode}")

    successes = 0
    failures = []

    if mode == "cpg":
        if server_mode:
            # Use the new server pool approach for CPG mode
            print(
                f"Processing {total} files with server pool in '{mode}' mode ...",
                file=sys.stderr,
            )

            # Create and start server manager
            server_manager = JoernServerManager(num_servers=workers)
            server_manager.start_servers()

            try:
                # Create tasks with server manager
                tasks = [
                    (fpath, src_root, out_root, server_manager) for fpath in src_files
                ]

                # Use ThreadPoolExecutor for better integration with server pool
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_file = {
                        executor.submit(process_file_cpg, task): task[0]
                        for task in tasks
                    }
                    pbar = tqdm(total=total, desc="Files processed", unit="file")
                    for future in as_completed(future_to_file):
                        src_file = future_to_file[future]
                        try:
                            file_path, ok, msg = future.result()
                        except Exception as e:
                            failures.append((src_file, f"Exception: {e}"))
                            print(
                                f"[ERROR] Unexpected exception for {src_file}: {e}",
                                file=sys.stderr,
                            )
                        else:
                            if ok:
                                successes += 1
                            else:
                                failures.append((file_path, msg))
                                print(f"[FAIL] {file_path}: {msg}", file=sys.stderr)
                        pbar.update(1)
                    pbar.close()
            finally:
                # Always shutdown servers
                server_manager.shutdown()
        else:
            # Use legacy approach for CPG mode
            tasks = [(fpath, src_root, out_root) for fpath in src_files]
            worker = process_file_cpg_legacy

            print(
                f"Processing {total} files with {workers} workers in '{mode}' mode (legacy) ...",
                file=sys.stderr,
            )
            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_to_file = {
                    executor.submit(worker, task): task[0] for task in tasks
                }
                pbar = tqdm(total=total, desc="Files processed", unit="file")
                for future in as_completed(future_to_file):
                    src_file = future_to_file[future]
                    try:
                        file_path, ok, msg = future.result()
                    except Exception as e:
                        failures.append((src_file, f"Exception: {e}"))
                        print(
                            f"[ERROR] Unexpected exception for {src_file}: {e}",
                            file=sys.stderr,
                        )
                    else:
                        if ok:
                            successes += 1
                        else:
                            failures.append((file_path, msg))
                            print(f"[FAIL] {file_path}: {msg}", file=sys.stderr)
                    pbar.update(1)
                pbar.close()

    elif mode == "template":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_template

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
                        f"[ERROR] Unexpected exception for {src_file}: {e}",
                        file=sys.stderr,
                    )
                else:
                    if ok:
                        successes += 1
                    else:
                        failures.append((file_path, msg))
                        print(f"[FAIL] {file_path}: {msg}", file=sys.stderr)
                pbar.update(1)
            pbar.close()

    elif mode == "dfg":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_dfg

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
                        f"[ERROR] Unexpected exception for {src_file}: {e}",
                        file=sys.stderr,
                    )
                else:
                    if ok:
                        successes += 1
                    else:
                        failures.append((file_path, msg))
                        print(f"[FAIL] {file_path}: {msg}", file=sys.stderr)
                pbar.update(1)
            pbar.close()

    elif mode == "ast":
        tasks = [(fpath, src_root, out_root) for fpath in src_files]
        worker = process_file_ast

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
                        f"[ERROR] Unexpected exception for {src_file}: {e}",
                        file=sys.stderr,
                    )
                else:
                    if ok:
                        successes += 1
                    else:
                        failures.append((file_path, msg))
                        print(f"[FAIL] {file_path}: {msg}", file=sys.stderr)
                pbar.update(1)
            pbar.close()
    else:
        raise ValueError(f"Invalid mode: {mode}")

    print(f"Done. Successes: {successes}, Failures: {len(failures)}", file=sys.stderr)
    if failures:
        print("Failures detailed below:", file=sys.stderr)
        for fpath, reason in failures:
            print(f"  {fpath}: {reason}", file=sys.stderr)
    else:
        print("All files processed successfully.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Batch processor: 'cpg' (joern-parse/export) or 'template' (tsx AST generator)."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["cpg", "template", "dfg", "ast"],
        help="Run mode: cpg, template, dfg, or ast.",
    )
    parser.add_argument(
        "--data", required=True, help="Path to source file or directory."
    )
    parser.add_argument("--output", help="Output directory for results (root).")
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
        "--server-mode",
        action="store_true",
        default=False,
        help="Use server pool mode for CPG processing (reduces startup overhead).",
    )
    parser.add_argument(
        "--replace-macro",
        action="store_true",
        default=False,
        help="Scan and replace #define macros in C/C++ code before processing.",
    )
    args = parser.parse_args()

    data_path = Path(args.data).resolve()

    if args.output:
        out_root = os.path.abspath(args.output)
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
        [".c", ".cpp"]
        if args.mode == "cpg"
        else [".json"]  # template: ONLY json inputs or dfg: ONLY json inputs
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
        src_root=src_root_dir,
        out_root=out_root,
        workers=args.workers,
        server_mode=args.server_mode,
    )


if __name__ == "__main__":
    main()
