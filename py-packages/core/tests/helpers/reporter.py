"""Test report generation utilities."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class TestReporter:
    """Generate test comparison reports."""

    def __init__(self, output_dir: Path):
        """Initialize reporter with output directory."""
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.reports: List[Dict[str, Any]] = []

    def add_comparison(
        self,
        test_name: str,
        is_equal: bool,
        differences: List[str],
        nodejs_output: Any = None,
        python_output: Any = None,
        execution_time: Dict[str, float] = None,
    ) -> None:
        """Add a comparison result."""
        report = {
            "test_name": test_name,
            "timestamp": datetime.now().isoformat(),
            "is_equal": is_equal,
            "differences": differences,
            "difference_count": len(differences),
            "execution_time": execution_time or {},
        }
        self.reports.append(report)

        # Save individual outputs if different
        if not is_equal:
            nodejs_file = self.output_dir / f"{test_name}_nodejs.json"
            python_file = self.output_dir / f"{test_name}_python.json"
            if nodejs_output is not None:
                with open(nodejs_file, "w", encoding="utf-8") as f:
                    json.dump(nodejs_output, f, indent=2, ensure_ascii=False)
            if python_output is not None:
                with open(python_file, "w", encoding="utf-8") as f:
                    json.dump(python_output, f, indent=2, ensure_ascii=False)

    def generate_summary(self) -> Dict[str, Any]:
        """Generate summary report."""
        total = len(self.reports)
        passed = sum(1 for r in self.reports if r["is_equal"])
        failed = total - passed

        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
            "tests": self.reports,
        }

        return summary

    def save_report(self, filename: str = "comparison_report.json") -> Path:
        """Save report to file."""
        summary = self.generate_summary()
        report_file = self.output_dir / filename
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        return report_file

    def print_summary(self) -> None:
        """Print summary to console."""
        summary = self.generate_summary()
        print("\n" + "=" * 80)
        print("TEST COMPARISON SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed']}")
        print(f"Failed: {summary['failed']}")
        print(f"Pass Rate: {summary['pass_rate']:.2f}%")
        print("=" * 80)

        if summary["failed"] > 0:
            print("\nFAILED TESTS:")
            for test in summary["tests"]:
                if not test["is_equal"]:
                    print(f"\n  {test['test_name']}:")
                    print(f"    Differences: {test['difference_count']}")
                    for diff in test["differences"][:5]:  # Show first 5 differences
                        print(f"      - {diff}")
                    if test["difference_count"] > 5:
                        print(f"      ... and {test['difference_count'] - 5} more")

        print()

