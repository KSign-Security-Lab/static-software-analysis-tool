"""The SEC-bench dataset: fetching it, reading it, and finding the crash in it.

Two hundred CVE instances in `eval-cve.jsonl` and a hundred OSS-Fuzz ones in
`eval-oss.jsonl`, 2.6MB and 1.2MB. The two hundred gigabytes people associate
with this benchmark are the built container images; the dataset itself fits in a
pocket, and downloading it is the only thing here that touches the network.

Every record carries its own `dockerfile`, `build_sh` and `secb_sh`, the CVE's
`bug_description`, an ASAN `sanitizer_report` with a real stack trace, and the
reference `patch`.

**`patch` is ground truth and never leaves this module for the agent.** It is
read by the evaluator and by nothing else. Handing the agent the files that
patch touches would be telling it where the bug is and then scoring it on
finding the bug -- a number that looks good and means nothing. `Instance.patch`
exists because the scorer needs it; `Instance.for_agent()` is what the runner is
allowed to pass on, and it does not include it.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from .config import SPLITS, BenchConfig

log = logging.getLogger(__name__)

#: Where the splits come from. The dataset is small and public, so this is a
#: plain download rather than the `datasets` library and its dependency tree.
DATASET_URL = "https://huggingface.co/datasets/SEC-bench/SEC-bench/resolve/main/data/eval-{split}.jsonl"

#: One frame of an AddressSanitizer backtrace:
#:
#:     #0 0x4e3e53 in njs_vmcode_interpreter /home/q1iq/.../src/njs_vmcode.c:802:27
#:
#: The column is optional -- not every frame has one -- and the path is absolute
#: on whatever machine built the report, which is why `candidate_paths` exists.
_FRAME = re.compile(
    r"^\s*#(?P<depth>\d+)\s+0x[0-9a-f]+\s+in\s+(?P<function>\S+)\s+(?P<path>[^\s:]+):(?P<line>\d+)(?::\d+)?",
    re.MULTILINE,
)

#: Extensions worth indexing. The report also names libc and compiler-runtime
#: frames; those are somebody else's source and not in the image.
SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp")


@dataclass(frozen=True)
class Frame:
    """One line of a backtrace."""

    depth: int
    function: str
    #: As written in the report: absolute, on the machine that produced it.
    path: str
    line: int

    @property
    def is_source(self) -> bool:
        return self.path.endswith(SOURCE_SUFFIXES)


@dataclass(frozen=True)
class Instance:
    """One benchmark instance, as the dataset ships it."""

    instance_id: str
    repo: str
    project_name: str
    lang: str
    work_dir: str
    sanitizer: str
    bug_description: str
    base_commit: str
    build_sh: str
    secb_sh: str
    dockerfile: str
    #: The reference fix. Ground truth: the evaluator's, never the agent's.
    patch: str
    exit_code: int
    sanitizer_report: str
    bug_report: str

    @classmethod
    def from_record(cls, record: dict) -> Instance:
        known = {f: record.get(f) for f in cls.__dataclass_fields__}
        known["exit_code"] = int(known.get("exit_code") or 0)
        return cls(**{k: (v if v is not None else "") if k != "exit_code" else v for k, v in known.items()})

    # -- what the agent may see ---------------------------------------------

    def for_agent(self) -> dict[str, str]:
        """Everything the runner is allowed to put in front of the model.

        Deliberately a separate shape rather than the record with a field
        removed: a subtraction is easy to forget to repeat, and this cannot
        leak `patch` by omission because it never mentions it.
        """
        return {
            "instance_id": self.instance_id,
            "project": self.project_name,
            "bug_description": self.bug_description,
            "sanitizer": self.sanitizer,
            "sanitizer_report": self.sanitizer_report,
        }

    # -- where the crash was ------------------------------------------------

    def frames(self) -> list[Frame]:
        """The backtrace, innermost first, source frames only."""
        found = [
            Frame(
                depth=int(m.group("depth")),
                function=m.group("function"),
                path=m.group("path"),
                line=int(m.group("line")),
            )
            for m in _FRAME.finditer(self.sanitizer_report or "")
        ]
        return [frame for frame in found if frame.is_source]

    def project_frames(self) -> list[Frame]:
        """The frames that are this project's own code.

        A backtrace runs off the end of the project and into libc and the
        compiler runtime -- `/build/glibc/csu/libc-start.c` is a `.c` file by
        every test except the one that matters. That source is not in the image
        and indexing it would spend a run reading somebody else's code.

        Recognised by the project marker in the path. If no frame has one -- a
        report produced somewhere that laid the tree out differently -- every
        source frame is kept, because a narrowing rule that matches nothing
        should widen rather than return an empty backtrace.
        """
        source = self.frames()
        owned = [frame for frame in source if _has_marker(frame.path, self.project_name)]
        return owned or source

    def crash_paths(self, depth: int = 1) -> list[str]:
        """Repo-relative paths for the crashing frame and `depth` callers above.

        Ordered innermost first and de-duplicated, so the file the sanitizer
        actually blamed is the first thing the agent is given.
        """
        wanted: list[str] = []
        for position, frame in enumerate(self.project_frames()):
            if position > depth:
                break
            resolved = candidate_paths(frame.path, self.project_name)
            if resolved and resolved[0] not in wanted:
                wanted.append(resolved[0])
        return wanted


def _has_marker(reported: str, project: str) -> bool:
    """Whether a path looks like it is inside `project`'s tree.

    The directory is often the project name with a commit or version glued on
    -- `njs_f65981b` -- so a prefix match rather than equality.
    """
    return any(
        part == project or part.startswith(f"{project}_") or part.startswith(f"{project}-")
        for part in Path(reported).parts
    )


def candidate_paths(reported: str, project: str) -> list[str]:
    """Repo-relative readings of an absolute path from someone else's machine.

    A report says `/home/q1iq/Documents/origin/njs_f65981b/src/njs_vmcode.c` and
    the container has `/src/njs/src/njs_vmcode.c`. Nothing in the record maps
    one to the other, so this proposes suffixes -- longest first -- and the
    caller takes the first that exists in the image.

    Longest first because the shortest suffix is the bare filename, and a
    project with `src/utils.c` and `test/utils.c` would otherwise resolve to
    whichever the filesystem answered with.
    """
    parts = [p for p in Path(reported).parts if p not in ("/", "")]
    # Anything after a directory that looks like the project is repo-relative.
    for index, part in enumerate(parts):
        if part == project or part.startswith(f"{project}_") or part.startswith(f"{project}-"):
            tail = parts[index + 1 :]
            if tail:
                return ["/".join(tail)]
    # No project marker: offer progressively shorter suffixes, longest first.
    return ["/".join(parts[i:]) for i in range(max(0, len(parts) - 4), len(parts))]


# -- fetching ----------------------------------------------------------------


def fetch(config: BenchConfig | None = None, splits: Sequence[str] = SPLITS) -> dict[str, int]:
    """Download the splits into `root/data`. Idempotent.

    The only network call in the sweep, and it is 3.8MB for both splits. Written
    to a temporary name and moved into place, so an interrupted download cannot
    leave a half-file that parses as a shorter benchmark.
    """
    config = config or BenchConfig()
    config.data_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for split in splits:
        target = config.data_dir / f"eval-{split}.jsonl"
        url = DATASET_URL.format(split=split)
        log.info("bench: fetching %s", url)
        staging = target.with_suffix(".jsonl.part")
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - a pinned https URL
            staging.write_bytes(response.read())
        staging.replace(target)
        counts[split] = sum(1 for _ in target.open(encoding="utf-8"))
    return counts


def load(config: BenchConfig | None = None) -> list[Instance]:
    """Every instance of the configured split, in file order."""
    config = config or BenchConfig()
    path = config.dataset_file
    if not path.exists():
        raise FileNotFoundError(f"{path} is not there; run `agent bench fetch` first")
    return [Instance.from_record(json.loads(line)) for line in _lines(path)]


def _lines(path: Path) -> Iterator[str]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield line


def select(instances: Sequence[Instance], config: BenchConfig | None = None) -> list[Instance]:
    """Narrow to what this sweep is about: named ids first, then the cap.

    An id that names nothing is an error rather than an empty sweep -- a typo in
    an instance id would otherwise look exactly like a benchmark with nothing to
    run, which is the kind of quiet nothing that wastes an afternoon.
    """
    config = config or BenchConfig()
    chosen = list(instances)

    if config.instances:
        by_id = {instance.instance_id: instance for instance in chosen}
        unknown = [name for name in config.instances if name not in by_id]
        if unknown:
            raise KeyError(f"no such instance(s) in split {config.split!r}: {', '.join(unknown)}")
        chosen = [by_id[name] for name in config.instances]

    if config.limit > 0:
        chosen = chosen[: config.limit]
    return chosen
