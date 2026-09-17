from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import List, Literal, Optional

Mode = Literal["cpg", "template", "ast", "dfg", "template-functions", "full", "f2a"]
COMMANDS: dict[str, tuple[str, str, str]] = {
    "cpg": (
        "Generate a Code Property Graph from source code",
        "source file or directory",
        "c,h,cpp,cc,cxx,hpp,hxx,java",
    ),
    "template": ("Generate Template artifacts from CPG data", "CPG file or directory", "json"),
    "ast": ("Generate Abstract Syntax Trees from CPG data", "CPG file or directory", "json"),
    "template-functions": (
        "Extract every function node of the Template, one file per function",
        "CPG file or directory",
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

TEMPLATE_STAGES: frozenset[str] = frozenset({"template", "ast", "template-functions", "dfg", "full"})


@dataclass
class CliOptions:
    mode: Mode
    data: str
    output: Optional[str] = None
    ext: List[str] = field(default_factory=list)
    replace_macro: bool = True
    keep_intermediate: bool = False
    workers: Optional[str] = None
    debug: bool = False
    verbose: bool = False
    representation: str = "all"
    copy_source: bool = False


def _add_common_arguments(parser: argparse.ArgumentParser, input_help: str, default_ext: str) -> None:
    parser.add_argument("data", nargs="?", help=f"Input {input_help}")
    parser.add_argument("-d", "--data", dest="data_flag", help=argparse.SUPPRESS)
    parser.add_argument("-o", "--output", help="Output directory (default: result/<mode>_<timestamp>)")
    parser.add_argument("--ext", default=default_ext, help="File extensions to process (comma-separated)")
    parser.add_argument("--keep-intermediate", action="store_true", help="Keep intermediate files")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")


class CliParser:
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
        subparsers = self.parser.add_subparsers(dest="mode", help="Command to run", required=True)

        for name, (help_text, input_help, default_ext) in COMMANDS.items():
            subparser = subparsers.add_parser(
                name,
                help=help_text,
                formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            )
            _add_common_arguments(subparser, input_help, default_ext)

            if name == "cpg":
                subparser.add_argument("--workers", default="4", help="Parallel workers for batch CPG generation")
                subparser.add_argument("--repr", default="all", help="Representation (ast, cfg, cpg14, all, ...)")
                subparser.add_argument(
                    "--copy-source", action="store_true", help="Copy original source files alongside CPG output"
                )
            else:
                subparser.add_argument("--workers", default="1", help="Parallel workers (CPG generation only)")

            if name in TEMPLATE_STAGES:
                subparser.add_argument(
                    "--replace-macro",
                    action="store_true",
                    default=True,
                    help="Fold a #define use into the expansion Joern inlined under it",
                )
                subparser.add_argument(
                    "--no-replace-macro",
                    dest="replace_macro",
                    action="store_false",
                    help="Leave macro uses as the pseudo-calls the CPG models them as",
                )

    def parse(self, argv: Optional[List[str]] = None) -> CliOptions:
        args = self.parser.parse_args(argv)
        data = args.data or args.data_flag
        if not data:
            self.parser.error(f"{args.mode}: an input path is required")

        ext_list: List[str] = []
        if getattr(args, "ext", None):
            ext_list = [e.strip() for e in args.ext.split(",") if e.strip()]

        return CliOptions(
            mode=args.mode,
            data=data,
            output=getattr(args, "output", None),
            ext=ext_list,
            replace_macro=getattr(args, "replace_macro", True),
            keep_intermediate=getattr(args, "keep_intermediate", False),
            workers=getattr(args, "workers", None),
            debug=getattr(args, "debug", False),
            verbose=getattr(args, "verbose", False),
            representation=getattr(args, "repr", "all"),
            copy_source=getattr(args, "copy_source", False),
        )
