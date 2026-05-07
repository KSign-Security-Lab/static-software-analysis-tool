"""Python test runner utilities."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


def run_python_endpoint(
    function_name: str,
    input_data: Any,
    core_path: Path,
    timeout: int = 60,
) -> Any:
    """
    Run a Python endpoint function with input data.

    Args:
        function_name: Name of the endpoint function (e.g., 'generate_template')
        input_data: Input data to pass to the function
        core_path: Path to Python core package
        timeout: Timeout in seconds

    Returns:
        Result from the Python function
    """
    # Create a temporary Python script
    func_name = function_name
    is_async = func_name in ['generate_cpg', 'generate_ast']
    script_content = f"""
import asyncio
import json
import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path('{core_path.absolute()}') / 'src'))

from core.endpoint import {func_name}

data = {json.dumps(input_data)}

async def main():
    try:
        func = {func_name}
        if {is_async}:
            result = await func(data)
        else:
            result = func(data)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'ERROR: {{str(e)}}', file=sys.stderr)
        sys.exit(1)

asyncio.run(main())
"""

    result = subprocess.run(
        [sys.executable, "-c", script_content],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=core_path.parent.parent,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Python execution failed: {result.stderr}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Python execution produced no output")

    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from Python: {e}. Output: {output[:200]}")


def run_python_cli(
    mode: str,
    input_path: Path,
    output_path: Path,
    core_path: Path,
    timeout: int = 120,
) -> None:
    """
    Run Python CLI command.

    Args:
        mode: CLI mode (cpg, template, ast, dfg, full)
        input_path: Path to input file or directory
        output_path: Path to output directory
        core_path: Path to Python core package
        timeout: Timeout in seconds
    """
    cli_path = core_path.parent / "cli" / "src" / "cli" / "__main__.py"
    if not cli_path.exists():
        raise FileNotFoundError(f"Python CLI not found at {cli_path}")

    cmd = [
        sys.executable,
        "-m",
        "cli",
        mode,
        "--data",
        str(input_path),
        "--output",
        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=core_path.parent.parent,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Python CLI failed: {result.stderr}")

