"""Comparison tests for DFG generation."""

import json
from pathlib import Path

import pytest

from ..helpers.comparator import compare_graphs
from ..helpers.nodejs_runner import run_nodejs_endpoint
from ..helpers.python_runner import run_python_endpoint
from ..helpers.reporter import TestReporter


@pytest.mark.asyncio
async def test_dfg_generation_comparison(
    cpg_dir: Path,
    python_core_path: Path,
    nodejs_core_path: Path,
    tmp_path: Path,
):
    """Compare DFG generation between Node.js and Python."""
    # Find CPG files
    cpg_files = list(cpg_dir.glob("*.json"))
    if not cpg_files:
        pytest.skip("No CPG files found in fixtures")

    reporter = TestReporter(tmp_path / "reports")

    for cpg_file in cpg_files[:3]:  # Test first 3 files
        with open(cpg_file, "r", encoding="utf-8") as f:
            cpg_data = json.load(f)

        test_name = f"dfg_{cpg_file.stem}"

        try:
            # Generate template first (both versions)
            nodejs_template = run_nodejs_endpoint("generateTemplate", cpg_data, nodejs_core_path)
            python_template = run_python_endpoint("generate_template", cpg_data, python_core_path)

            # Generate AST
            nodejs_ast = run_nodejs_endpoint("generateAst", nodejs_template, nodejs_core_path)
            python_ast = run_python_endpoint("generate_ast", python_template, python_core_path)

            # Generate DFG
            nodejs_dfg = run_nodejs_endpoint("generateDfg", {"cpg": cpg_data, "asts": nodejs_ast}, nodejs_core_path)
            python_dfg = run_python_endpoint("generate_dfg", {"cpg": cpg_data, "asts": python_ast}, python_core_path)

            # Compare DFG graphs
            if isinstance(nodejs_dfg, list) and isinstance(python_dfg, list):
                for i, (nj_dfg, py_dfg) in enumerate(zip(nodejs_dfg, python_dfg)):
                    is_equal, differences = compare_graphs(nj_dfg, py_dfg)
                    reporter.add_comparison(
                        f"{test_name}_graph_{i}",
                        is_equal,
                        differences,
                        nj_dfg,
                        py_dfg,
                    )
            else:
                is_equal, differences = compare_graphs(nodejs_dfg, python_dfg)
                reporter.add_comparison(
                    test_name,
                    is_equal,
                    differences,
                    nodejs_dfg,
                    python_dfg,
                )

        except Exception as e:
            reporter.add_comparison(
                test_name,
                False,
                [f"Execution error: {str(e)}"],
            )
            pytest.fail(f"Test {test_name} failed with error: {e}")

    # Generate report
    report_file = reporter.save_report()
    reporter.print_summary()
    print(f"\nFull report saved to: {report_file}")

