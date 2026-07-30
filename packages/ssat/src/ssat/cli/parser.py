"""CLI argument parser.

Every subcommand takes the same options apart from the CPG-specific ones, so
they are declared once in :func:`_add_common_arguments` rather than repeated per
subparser (which is how they drifted apart before).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from ..cpg.backends import BACKEND_NAMES

Mode = Literal["cpg", "template", "ast", "dfg", "template-functions", "full", "f2a"]

DEFAULT_BACKEND = "jpype"

#: subcommand -> (help text, default input description, default extensions)
COMMANDS: dict[str, tuple[str, str, str]] = {
    "cpg": (
        "Generate a Code Property Graph from source code",
        "source file or directory",
        "c,h,cpp,cc,cxx,hpp,hxx,java",
    ),
    "template": ("Generate Template artifacts from CPG data", "CPG file or directory", "json"),
    "ast": ("Generate Abstract Syntax Trees from CPG data", "CPG file or directory", "json"),
    "template-functions": (
        "Extract every function node from a Template, one file per function",
        "Template file or directory",
        "json",
    ),
    "dfg": ("Generate def-use Data Flow Graphs from CPG data", "CPG file or directory", "json"),
    "full": (
        "Generate AST + DFG per function, in the schema the GNN trainer reads",
        "CPG file or directory",
        "json",
    ),
    "f2a": (
        "Extract OCPP-native source-to-sink evidence candidates from CPG data",
        "CPG file or directory",
        "json",
    ),
}


@dataclass
class CliOptions:
    """Parsed CLI options."""

    mode: Mode
    data: str
    output: Optional[str] = None
    ext: List[str] = field(default_factory=list)
    replace_macro: bool = True
    keep_intermediate: bool = False
    workers: Optional[str] = None
    debug: bool = False
    verbose: bool = False
    backend: str = DEFAULT_BACKEND
    representation: str = "all"
    export_format: str = "graphson"
    copy_source: bool = False


def _add_common_arguments(parser: argparse.ArgumentParser, input_help: str, default_ext: str) -> None:
    """Options every subcommand accepts."""
    parser.add_argument("-d", "--data", required=True, help=f"Input {input_help}")
    parser.add_argument("-o", "--output", help="Output directory (default: result/<mode>_<timestamp>)")
    parser.add_argument("--ext", default=default_ext, help="File extensions to process (comma-separated)")
    parser.add_argument(
        "--backend",
        default=DEFAULT_BACKEND,
        choices=BACKEND_NAMES,
        help="CPG engine: 'jpype' runs Joern in-process, 'docker' uses the Joern container",
    )
    parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")


class CliParser:
    """CLI argument parser."""

    def __init__(self) -> None:
        self.parser = argparse.ArgumentParser(
            prog="ssat",
            description=(
                "Static Software Analysis Tool - convert source code (C/C++/Java) "
                "into CPG, Template, AST, DFG and F2-A evidence"
            ),
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        self.parser.add_argument("--version", action="version", version="2.4.3")
        self.setup_subcommands()

    def setup_subcommands(self) -> None:
        """Declare one subparser per mode."""
        subparsers = self.parser.add_subparsers(dest="mode", help="Command to run", required=True)

        for name, (help_text, input_help, default_ext) in COMMANDS.items():
            subparser = subparsers.add_parser(
                name,
                help=help_text,
                formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            )
            _add_common_arguments(subparser, input_help, default_ext)

            if name == "cpg":
                # Only CPG generation parallelises: batch_generate_cpg drives a
                # real process pool. Later stages are sequential CPU work.
                subparser.add_argument("--workers", default="4", help="Parallel workers for batch CPG generation")
                subparser.add_argument("--repr", default="all", help="Representation (ast, cfg, cpg14, all, ...)")
                subparser.add_argument(
                    "-f", "--format", default="graphson", help="Export format (dot, graphson, graphml, ...)"
                )
                subparser.add_argument(
                    "--replace-macro", action="store_true", default=True, help="Replace macros in source files"
                )
                subparser.add_argument(
                    "--no-replace-macro", dest="replace_macro", action="store_false", help="Skip macro replacement"
                )
                subparser.add_argument(
                    "--copy-source", action="store_true", help="Copy original source files alongside CPG output"
                )
            else:
                subparser.add_argument("--workers", default="1", help="Parallel workers (CPG generation only)")

    def parse(self, argv: Optional[List[str]] = None) -> CliOptions:
        """Parse command line arguments."""
        args = self.parser.parse_args(argv)

        ext_list: List[str] = []
        if getattr(args, "ext", None):
            ext_list = [e.strip() for e in args.ext.split(",") if e.strip()]

        return CliOptions(
            mode=args.mode,
            data=args.data,
            output=getattr(args, "output", None),
            ext=ext_list,
            replace_macro=getattr(args, "replace_macro", True),
            keep_intermediate=getattr(args, "keep_intermediate", False),
            workers=getattr(args, "workers", None),
            debug=getattr(args, "debug", False),
            verbose=getattr(args, "verbose", False),
            backend=getattr(args, "backend", DEFAULT_BACKEND),
            representation=getattr(args, "repr", "all"),
            export_format=getattr(args, "format", "graphson"),
            copy_source=getattr(args, "copy_source", False),
        )
