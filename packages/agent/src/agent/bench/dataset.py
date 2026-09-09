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
DATASET_URL = "https://huggingface.co/datasets/SEC-bench/SEC-bench/resolve/main/data/eval-{split}.jsonl"
_FRAME = re.compile(
    r"^\s*#(?P<depth>\d+)\s+0x[0-9a-f]+\s+in\s+(?P<function>\S+)\s+(?P<path>[^\s:]+):(?P<line>\d+)(?::\d+)?",
    re.MULTILINE,
)

SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp")


@dataclass(frozen=True)
class Frame:
    depth: int
    function: str
    path: str
    line: int

    @property
    def is_source(self) -> bool:
        return self.path.endswith(SOURCE_SUFFIXES)


@dataclass(frozen=True)
class Instance:
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
    patch: str
    exit_code: int
    sanitizer_report: str
    bug_report: str

    @classmethod
    def from_record(cls, record: dict) -> Instance:
        known = {f: record.get(f) for f in cls.__dataclass_fields__}
        known["exit_code"] = int(known.get("exit_code") or 0)
        return cls(**{k: (v if v is not None else "") if k != "exit_code" else v for k, v in known.items()})

    def for_agent(self) -> dict[str, str]:
        return {
            "instance_id": self.instance_id,
            "project": self.project_name,
            "bug_description": self.bug_description,
            "sanitizer": self.sanitizer,
            "sanitizer_report": self.sanitizer_report,
        }

    def frames(self) -> list[Frame]:
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
        source = [frame for frame in self.frames() if not _is_foreign(frame.path)]
        owned = [frame for frame in source if _has_marker(frame.path, self.project_name)]
        return owned or source

    def crash_paths(self, depth: int = 1) -> list[str]:
        wanted: list[str] = []
        for readings in self.crash_candidates(depth):
            if readings[0] not in wanted:
                wanted.append(readings[0])
        return wanted

    def crash_candidates(self, depth: int = 1) -> list[list[str]]:
        found: list[list[str]] = []
        seen: set[str] = set()
        for position, frame in enumerate(self.project_frames()):
            if position > depth:
                break
            readings = [r for r in candidate_paths(frame.path, self.project_name) if r]
            if readings and readings[0] not in seen:
                seen.add(readings[0])
                found.append(readings)
        return found


def _has_marker(reported: str, project: str) -> bool:
    return any(_is_marker(part, project) for part in Path(reported).parts)


def candidate_paths(reported: str, project: str) -> list[str]:
    parts = [p for p in Path(reported).parts if p not in ("/", "", ".", "..")]
    marked = [
        "/".join(parts[index + 1 :])
        for index, part in enumerate(parts)
        if _is_marker(part, project) and parts[index + 1 :]
    ]
    if marked:
        return marked

    return ["/".join(parts[i:]) for i in range(max(0, len(parts) - 4), len(parts))]


_FOREIGN = ("/usr/", "/lib/", "/build/glibc", "/usr/include", "/opt/rh/")


def _is_foreign(reported: str) -> bool:
    return reported.startswith(_FOREIGN)


def _is_marker(part: str, project: str) -> bool:
    return part == project or part.startswith(f"{project}_") or part.startswith(f"{project}-")


def fetch(config: BenchConfig | None = None, splits: Sequence[str] = SPLITS) -> dict[str, int]:
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
