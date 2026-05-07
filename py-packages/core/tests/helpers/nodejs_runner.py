"""Node.js test runner utilities."""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def run_nodejs_endpoint(
    function_name: str,
    input_data: Any,
    core_path: Path,
    timeout: int = 60,
) -> Any:
    """
    Run a Node.js endpoint function with input data.

    Args:
        function_name: Name of the endpoint function (e.g., 'generateTemplate')
        input_data: Input data to pass to the function
        core_path: Path to Node.js core package
        timeout: Timeout in seconds

    Returns:
        Result from the Node.js function
    """
    # Create a temporary Node.js script
    script_content = f"""
const core = require('{core_path.absolute()}/dist/endpoint/index.js');
const data = {json.dumps(input_data)};

core.{function_name}(data)
  .then(result => {{
    console.log(JSON.stringify(result, null, 2));
  }})
  .catch(error => {{
    console.error('ERROR:', error.message);
    process.exit(1);
  }});
"""

    result = subprocess.run(
        ["node", "-e", script_content],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=core_path.parent.parent,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Node.js execution failed: {result.stderr}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Node.js execution produced no output")

    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from Node.js: {e}. Output: {output[:200]}")


def run_nodejs_cli(
    mode: str,
    input_path: Path,
    output_path: Path,
    core_path: Path,
    timeout: int = 120,
) -> None:
    """
    Run Node.js CLI command.

    Args:
        mode: CLI mode (cpg, template, ast, dfg, full)
        input_path: Path to input file or directory
        output_path: Path to output directory
        core_path: Path to Node.js core package
        timeout: Timeout in seconds
    """
    cli_path = core_path.parent / "cli" / "dist" / "index.js"
    if not cli_path.exists():
        raise FileNotFoundError(f"Node.js CLI not found at {cli_path}")

    cmd = [
        "node",
        str(cli_path),
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
        raise RuntimeError(f"Node.js CLI failed: {result.stderr}")

