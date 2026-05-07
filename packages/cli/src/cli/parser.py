"""CLI argument parser."""

import argparse
from typing import Dict, Literal, Optional

Mode = Literal["cpg", "template", "ast", "dfg", "template-functions", "full"]


class CliOptions:
    """CLI options structure."""

    def __init__(
        self,
        mode: Mode,
        data: str,
        output: Optional[str] = None,
        ext: Optional[list[str]] = None,
        replace_macro: bool = True,
        keep_intermediate: bool = False,
        workers: Optional[str] = None,
        debug: bool = False,
        verbose: bool = False,
        representation: str = "all",
        export_format: str = "graphson",
    ):
        self.mode = mode
        self.data = data
        self.output = output
        self.ext = ext or []
        self.replace_macro = replace_macro
        self.keep_intermediate = keep_intermediate
        self.workers = workers
        self.debug = debug
        self.verbose = verbose
        self.representation = representation
        self.export_format = export_format


class CliParser:
    """CLI argument parser."""

    def __init__(self):
        """Initialize parser."""
        self.parser = argparse.ArgumentParser(
            prog="ssat",
            description="Static Software Analysis Tool - Convert C source code to various representations",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        self.parser.add_argument("--version", action="version", version="2.4.3")
        self.setup_subcommands()

    def setup_subcommands(self) -> None:
        """Setup subcommands."""
        subparsers = self.parser.add_subparsers(dest="mode", help="Command to run", required=True)

        # Common formatter for sub-parsers
        fmt = argparse.ArgumentDefaultsHelpFormatter

        # CPG command
        cpg_parser = subparsers.add_parser(
            "cpg",
            help="Generate Code Property Graph from C source code",
            formatter_class=fmt,
        )
        cpg_parser.add_argument("-d", "--data", required=True, help="Input C source file or directory")
        cpg_parser.add_argument("-o", "--output", help="Output directory (default: result/cpg_<timestamp>)")
        cpg_parser.add_argument("--ext", default="c", help="File extensions to process (comma-separated)")
        cpg_parser.add_argument("--repr", default="all", help="Representation (ast, cfg, cpg14, all, etc.)")
        cpg_parser.add_argument("-f", "--format", default="graphson", help="Export format (dot, graphson, graphml, etc.)")
        cpg_parser.add_argument("--replace-macro", action="store_true", default=True, help="Replace macros in source files")
        cpg_parser.add_argument("--no-replace-macro", dest="replace_macro", action="store_false", help="Skip macro replacement")
        cpg_parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
        cpg_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
        cpg_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

        # Template command
        template_parser = subparsers.add_parser(
            "template",
            help="Generate Template artifacts from CPG data",
            formatter_class=fmt,
        )
        template_parser.add_argument("-d", "--data", required=True, help="Input CPG file or directory")
        template_parser.add_argument("-o", "--output", help="Output directory (default: result/template_<timestamp>)")
        template_parser.add_argument("--ext", default="json", help="File extensions to process (comma-separated)")
        template_parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
        template_parser.add_argument("--workers", default="1", help="Number of parallel workers")
        template_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
        template_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

        # AST command
        ast_parser = subparsers.add_parser(
            "ast",
            help="Generate Abstract Syntax Tree from Template data",
            formatter_class=fmt,
        )
        ast_parser.add_argument("-d", "--data", required=True, help="Input Template file or directory")
        ast_parser.add_argument("-o", "--output", help="Output directory (default: result/ast_<timestamp>)")
        ast_parser.add_argument("--ext", default="json", help="File extensions to process (comma-separated)")
        ast_parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
        ast_parser.add_argument("--workers", default="1", help="Number of parallel workers")
        ast_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
        ast_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

        # Template-functions command
        tf_parser = subparsers.add_parser(
            "template-functions",
            help="Extract all function nodes from Template recursively and save per-function",
            formatter_class=fmt,
        )
        tf_parser.add_argument("-d", "--data", required=True, help="Input Template file or directory")
        tf_parser.add_argument("-o", "--output", help="Output directory (default: result/template_functions_<timestamp>)")
        tf_parser.add_argument("--ext", default="json", help="File extensions to process (comma-separated)")
        tf_parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
        tf_parser.add_argument("--workers", default="1", help="Number of parallel workers")
        tf_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
        tf_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

        # DFG command
        dfg_parser = subparsers.add_parser(
            "dfg",
            help="Generate Data Flow Graph from Template data",
            formatter_class=fmt,
        )
        dfg_parser.add_argument("-d", "--data", required=True, help="Input Template file or directory")
        dfg_parser.add_argument("-o", "--output", help="Output directory (default: result/dfg_<timestamp>)")
        dfg_parser.add_argument("--ext", default="json", help="File extensions to process (comma-separated)")
        dfg_parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
        dfg_parser.add_argument("--workers", default="1", help="Number of parallel workers")
        dfg_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
        dfg_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

        # Full command
        full_parser = subparsers.add_parser(
            "full",
            help="Generate Full artifacts from Template data",
            formatter_class=fmt,
        )
        full_parser.add_argument("-d", "--data", required=True, help="Input Template file or directory")
        full_parser.add_argument("-o", "--output", help="Output directory (default: result/full_<timestamp>)")
        full_parser.add_argument("--ext", default="json", help="File extensions to process (comma-separated)")
        full_parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
        full_parser.add_argument("--workers", default="1", help="Number of parallel workers")
        full_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
        full_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    def parse(self) -> CliOptions:
        """Parse command line arguments."""
        args = self.parser.parse_args()

        # Parse extensions
        ext_list = []
        if getattr(args, "ext", None):
            ext_list = [e.strip() for e in args.ext.split(",")]

        return CliOptions(
            mode=args.mode,  # type: ignore
            data=args.data,
            output=getattr(args, "output", None),
            ext=ext_list,
            replace_macro=getattr(args, "replace_macro", True),
            keep_intermediate=getattr(args, "keep_intermediate", False),
            workers=getattr(args, "workers", None),
            debug=getattr(args, "debug", False),
            verbose=getattr(args, "verbose", False),
            representation=getattr(args, "repr", "all"),
            export_format=getattr(args, "format", "graphson"),
        )
