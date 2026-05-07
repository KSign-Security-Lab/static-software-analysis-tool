"""Comparison tests for template generation."""

import json
from pathlib import Path

import pytest

from ..helpers.comparator import compare_outputs
from ..helpers.nodejs_runner import run_nodejs_endpoint
from ..helpers.python_runner import run_python_endpoint
from ..helpers.reporter import TestReporter


@pytest.mark.asyncio
async def test_template_generation_comparison(
    cpg_dir: Path,
    python_core_path: Path,
    nodejs_core_path: Path,
    tmp_path: Path,
):
    """Compare template generation between Node.js and Python."""
    # Find CPG files
    cpg_files = list(cpg_dir.glob("*.json"))
    if not cpg_files:
        pytest.skip("No CPG files found in fixtures")

    reporter = TestReporter(tmp_path / "reports")

    for cpg_file in cpg_files[:3]:  # Test first 3 files
        with open(cpg_file, "r", encoding="utf-8") as f:
            cpg_data = json.load(f)

        test_name = f"template_{cpg_file.stem}"

        try:
            # Run Node.js version
            nodejs_result = run_nodejs_endpoint("generateTemplate", cpg_data, nodejs_core_path)

            # Run Python version
            python_result = run_python_endpoint("generate_template", cpg_data, python_core_path)

            # Compare outputs
            is_equal, differences = compare_outputs(nodejs_result, python_result, ignore_order=True)

            reporter.add_comparison(
                test_name,
                is_equal,
                differences,
                nodejs_result,
                python_result,
            )

            if not is_equal:
                print(f"\n{test_name} FAILED:")
                for diff in differences[:10]:
                    print(f"  - {diff}")

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

