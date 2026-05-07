"""Comparison tests for full pipeline."""

import json
from pathlib import Path

import pytest

from ..helpers.comparator import compare_outputs
from ..helpers.nodejs_runner import run_nodejs_endpoint
from ..helpers.python_runner import run_python_endpoint
from ..helpers.reporter import TestReporter


@pytest.mark.asyncio
async def test_full_pipeline_comparison(
    c_sources_dir: Path,
    python_core_path: Path,
    nodejs_core_path: Path,
    tmp_path: Path,
):
    """Compare full pipeline (CPG -> Template -> AST -> DFG) between Node.js and Python."""
    # Find C source files
    c_files = list(c_sources_dir.glob("*.c"))
    if not c_files:
        pytest.skip("No C source files found in fixtures")

    reporter = TestReporter(tmp_path / "reports")

    for c_file in c_files[:2]:  # Test first 2 files
        test_name = f"full_pipeline_{c_file.stem}"

        try:
            # Generate CPG
            import asyncio
            nodejs_cpg = run_nodejs_endpoint("generateCpg", str(c_file), nodejs_core_path)
            python_cpg = await asyncio.to_thread(run_python_endpoint, "generate_cpg", str(c_file), python_core_path)

            # Generate Template
            nodejs_template = run_nodejs_endpoint("generateTemplate", nodejs_cpg, nodejs_core_path)
            python_template = run_python_endpoint("generate_template", python_cpg, python_core_path)

            # Compare templates
            template_equal, template_diffs = compare_outputs(nodejs_template, python_template, ignore_order=True)
            reporter.add_comparison(
                f"{test_name}_template",
                template_equal,
                template_diffs,
                nodejs_template,
                python_template,
            )

            # Generate AST
            nodejs_ast = run_nodejs_endpoint("generateAst", nodejs_template, nodejs_core_path)
            python_ast = await asyncio.to_thread(run_python_endpoint, "generate_ast", python_template, python_core_path)

            # Compare ASTs
            ast_equal, ast_diffs = compare_outputs(nodejs_ast, python_ast, ignore_order=True)
            reporter.add_comparison(
                f"{test_name}_ast",
                ast_equal,
                ast_diffs,
                nodejs_ast,
                python_ast,
            )

            # Generate DFG
            nodejs_dfg = run_nodejs_endpoint("generateDfg", {"cpg": nodejs_cpg, "asts": nodejs_ast}, nodejs_core_path)
            python_dfg = run_python_endpoint("generate_dfg", {"cpg": python_cpg, "asts": python_ast}, python_core_path)

            # Compare DFGs
            dfg_equal, dfg_diffs = compare_outputs(nodejs_dfg, python_dfg, ignore_order=True)
            reporter.add_comparison(
                f"{test_name}_dfg",
                dfg_equal,
                dfg_diffs,
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

