"""Bare `ssat` on a terminal: pick the stage, the paths and the options by arrow key.

Nothing here runs a stage. It assembles the same argv you would have typed and
hands it back, so the interactive path and the typed one go through one parser.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, List, Optional, Sequence, TextIO, Tuple, TypeVar

from .parser import COMMANDS, TEMPLATE_STAGES

SOURCE_EXTS: Tuple[str, ...] = ("c", "h", "cpp", "cc", "cxx", "hpp", "hxx", "java")
CPG_EXTS: Tuple[str, ...] = ("json",)
SKIP_DIRS = frozenset({".git", ".venv", ".next", ".mypy_cache", ".pytest_cache", "__pycache__", "node_modules"})

CHAIN = "cpg+full"

UP, DOWN, ENTER, QUIT = "up", "down", "enter", "quit"

DIM, BOLD, RESET = "\x1b[2m", "\x1b[1m", "\x1b[0m"

T = TypeVar("T")

ReadKey = Callable[[], str]
Run = Callable[[List[str]], None]


@dataclass(frozen=True)
class Choice(Generic[T]):
    label: str
    value: T
    hint: str = ""


def read_key() -> str:
    ch = _read_raw()
    if ch in (UP, DOWN):
        return ch
    if ch in ("\x1b[A", "\x1bOA", "k", "\x10"):
        return UP
    if ch in ("\x1b[B", "\x1bOB", "j", "\x0e"):
        return DOWN
    if ch in ("\r", "\n"):
        return ENTER
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch in ("q", "\x1b", "\x04"):
        return QUIT
    return ch


def _read_raw() -> str:
    """Straight off the descriptor: sys.stdin buffers, and a buffered read of the
    ESC swallows the rest of the arrow with it.
    """
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):  # arrows arrive as two calls
            return {"H": UP, "P": DOWN}.get(msvcrt.getwch(), "")
        return ch

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1).decode(errors="ignore")
        if ch == "\x1b" and select.select([fd], [], [], 0.05)[0]:
            ch += os.read(fd, 2).decode(errors="ignore")
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def select_one(
    title: str,
    choices: Sequence[Choice[T]],
    *,
    read: ReadKey = read_key,
    out: TextIO = sys.stdout,
) -> Optional[T]:
    if not choices:
        return None

    index = 0
    out.write(f"\n{BOLD}{title}{RESET}\n")
    _draw(choices, index, out)
    while True:
        key = read()
        if key == UP:
            index = (index - 1) % len(choices)
        elif key == DOWN:
            index = (index + 1) % len(choices)
        elif key == ENTER:
            _rewind(len(choices), out)
            _collapse(choices[index], out)
            return choices[index].value
        elif key == QUIT:
            _rewind(len(choices), out)
            out.write(f"\x1b[0J{DIM}  cancelled{RESET}\n")
            return None
        else:
            continue
        _rewind(len(choices), out)
        _draw(choices, index, out)


def _draw(choices: Sequence[Choice[T]], index: int, out: TextIO) -> None:
    for n, choice in enumerate(choices):
        mark = "❯" if n == index else " "
        hint = f"  {DIM}{choice.hint}{RESET}" if choice.hint else ""
        body = f"{BOLD}{choice.label}{RESET}" if n == index else choice.label
        out.write(f"\x1b[2K  {mark} {body}{hint}\n")


def _collapse(choice: Choice[T], out: TextIO) -> None:
    hint = f"  {DIM}{choice.hint}{RESET}" if choice.hint else ""
    out.write(f"\x1b[2K  {DIM}❯{RESET} {choice.label}{hint}\n\x1b[0J")


def _rewind(lines: int, out: TextIO) -> None:
    if lines > 0:
        out.write(f"\x1b[{lines}A")


def browse(
    title: str,
    start: Path,
    *,
    exts: Sequence[str] = (),
    read: ReadKey = read_key,
    out: TextIO = sys.stdout,
) -> Optional[Path]:
    current = start.resolve()
    while True:
        choices: List[Choice[Path]] = [Choice("[ use this directory ]", current, _display(current))]
        if current.parent != current:
            choices.append(Choice("..", current.parent, "up one"))
        for entry in _entries(current, exts):
            if entry.is_dir():
                choices.append(Choice(f"{entry.name}/", entry))
            else:
                choices.append(Choice(entry.name, entry, _size(entry)))

        picked = select_one(f"{title}  {DIM}{_display(current)}{RESET}", choices, read=read, out=out)
        if picked is None:
            return None
        if picked == current or picked.is_file():
            return picked
        current = picked


def _entries(directory: Path, exts: Sequence[str]) -> List[Path]:
    try:
        items = list(directory.iterdir())
    except OSError:
        return []
    wanted = {f".{e}" for e in exts}
    dirs = [p for p in items if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")]
    files = [p for p in items if p.is_file() and p.suffix in wanted]
    return sorted(dirs, key=lambda p: p.name.lower()) + sorted(files, key=lambda p: p.name.lower())


def _display(path: Path) -> str:
    try:
        return f"./{path.relative_to(Path.cwd())}" if path != Path.cwd() else "."
    except ValueError:
        return str(path)


def _size(path: Path) -> str:
    kb = path.stat().st_size / 1024
    return f"{kb:,.0f} KB" if kb >= 1 else f"{path.stat().st_size} B"


def exts_for(path: Path, candidates: Sequence[str], *, read: ReadKey = read_key, out: TextIO = sys.stdout) -> List[str]:
    """What to pass as --ext, asked only when a directory holds both kinds."""
    if path.is_file():
        return [path.suffix.lstrip(".")]

    present = {p.suffix.lstrip(".") for p in path.rglob("*") if p.is_file() and p.suffix.lstrip(".") in candidates}
    source = sorted(present & set(SOURCE_EXTS))
    cpg = sorted(present & set(CPG_EXTS))
    if source and cpg:
        picked = select_one(
            "That directory holds both. Which one?",
            [
                Choice("CPG json", cpg, "already generated"),
                Choice(f"source  .{', .'.join(source)}", source, "the CPG is generated in memory"),
            ],
            read=read,
            out=out,
        )
        return list(picked) if picked else []
    return source or cpg or list(candidates)


def build_argv(
    mode: str,
    data: Path,
    output: Optional[Path],
    exts: Sequence[str],
    *,
    replace_macro: bool = True,
    workers: Optional[int] = None,
) -> List[str]:
    argv = [mode, _display(data)]
    if output is not None:
        argv += ["-o", _display(output)]
    if exts:
        argv += ["--ext", ",".join(exts)]
    if mode in TEMPLATE_STAGES and not replace_macro:
        argv.append("--no-replace-macro")
    if mode == "cpg" and workers is not None:
        argv += ["--workers", str(workers)]
    return argv


def _stage_choices() -> List[Choice[str]]:
    choices = [Choice(mode, mode, help_text) for mode, (help_text, _, _) in COMMANDS.items()]
    choices.append(
        Choice(
            CHAIN,
            CHAIN,
            "source -> CPG -> AST + DFG per function, keeping the CPG for the other stages",
        )
    )
    return choices


def _plan(read: ReadKey, out: TextIO, root: Path) -> Optional[List[List[str]]]:
    mode = select_one("What do you want to run?", _stage_choices(), read=read, out=out)
    if mode is None:
        return None

    candidates = SOURCE_EXTS if mode in ("cpg", CHAIN) else SOURCE_EXTS + CPG_EXTS
    data = browse("Input", root, exts=candidates, read=read, out=out)
    if data is None:
        return None

    exts = exts_for(data, candidates, read=read, out=out)
    stamp = f"{'extract' if mode == CHAIN else mode}_{int(time.time())}"
    default_out = root / "result" / stamp
    where = [
        Choice(_display(default_out), "default", "the default"),
        Choice("somewhere else…", "browse", "pick a directory"),
    ]
    answer = select_one("Where should it write?", where, read=read, out=out)
    if answer is None:  # a value of its own, so backing out is not "somewhere else"
        return None
    output = default_out
    if answer == "browse":
        chosen = browse("Output directory", root, read=read, out=out)
        if chosen is None:
            return None
        output = chosen / stamp

    replace_macro = True
    if mode in TEMPLATE_STAGES or mode == CHAIN:
        folded = select_one(
            "What about macro uses?",
            [
                Choice("fold each into the expansion Joern inlined under it", True, "the default"),
                Choice("leave them as the pseudo-calls the CPG models them as", False, "--no-replace-macro"),
            ],
            read=read,
            out=out,
        )
        if folded is None:
            return None
        replace_macro = folded

    workers: Optional[int] = None
    if mode in ("cpg", CHAIN):
        workers = select_one(
            "How many CPG workers?",
            [Choice(str(n), n, "one JVM each, and the memory to match") for n in (1, 2, 4, 8)],
            read=read,
            out=out,
        )
        if workers is None:
            return None

    if mode == CHAIN:
        cpg_dir = output / "cpg"
        return [
            build_argv("cpg", data, cpg_dir, exts, workers=workers),
            build_argv("full", cpg_dir, output / "full", CPG_EXTS, replace_macro=replace_macro),
        ]
    return [build_argv(mode, data, output, exts, replace_macro=replace_macro, workers=workers)]


def run_interactive(
    run: Run, *, read: ReadKey = read_key, out: TextIO = sys.stdout, root: Optional[Path] = None
) -> int:
    root = root or Path.cwd()
    out.write(f"\n{BOLD}SSAT{RESET}  {DIM}arrow keys to move, enter to pick, q to quit{RESET}\n")

    while True:
        try:
            plan = _plan(read, out, root)
        except KeyboardInterrupt:
            out.write("\n")
            return 130
        if plan is None:
            return 0

        printed = "\n".join(f"  ssat {' '.join(argv)}" for argv in plan)
        out.write(f"\n{DIM}{printed}{RESET}\n")
        decision = select_one(
            "Run it?",
            [Choice("run", "run"), Choice("start over", "again"), Choice("quit", "quit")],
            read=read,
            out=out,
        )
        if decision == "quit" or decision is None:
            return 0
        if decision == "again":
            continue

        out.write("\n")
        for argv in plan:
            run(argv)
        return 0
