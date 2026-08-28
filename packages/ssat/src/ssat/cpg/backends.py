"""CPG generation backends: two engines behind one interface.

Both produce the same Joern GraphSON document; they differ only in how Joern is
invoked.

``jpype``
    Joern's JARs run in a JVM inside this process. No Docker, no subprocess.
    Fast after the first call (the JVM stays warm), which is what the web UI
    needs. Requires a local Joern install -- see ``JOERN_HOME``.

``docker``
    ``docker exec`` into a running Joern container. No local Joern install
    needed, and it is the engine the parallel batch driver uses
    (:func:`ssat.cpg.generator.batch_generate_cpg`).

Pick one with :func:`get_backend`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Protocol, runtime_checkable

DEFAULT_TIMEOUT_SECONDS = 300


def count_methods(graphson: Dict[str, Any]) -> int:
    """Count METHOD vertices in a GraphSON document.

    The previous counter looked for a top-level ``method`` key, which
    joern-export's GraphSON does not contain, so it always returned 0. The web
    API carried its own corrected copy; this is now the only implementation.
    """
    value = graphson.get("@value") if isinstance(graphson, dict) else None
    vertices = value.get("vertices", []) if isinstance(value, dict) else []
    return sum(1 for v in vertices if isinstance(v, dict) and v.get("label") == "METHOD")


@dataclass(frozen=True)
class CpgResult:
    """A generated CPG plus how it was produced."""

    graphson: Dict[str, Any]
    method_count: int
    backend: str

    @property
    def document(self) -> Dict[str, Any]:
        """The ``{"export": ...}`` shape the template pipeline consumes."""
        return {"export": self.graphson}


@runtime_checkable
class CpgBackend(Protocol):
    """One way of turning source text into a CPG GraphSON document."""

    name: str

    def is_available(self) -> bool:
        """True if this backend can run here (JARs present / container up)."""

    def generate(self, source: str, *, filename: str = "main.c", representation: str = "all") -> CpgResult:
        """Generate a CPG from source text."""


class EmbeddedBackend:
    """In-process Joern via JPype."""

    name = "jpype"

    def is_available(self) -> bool:
        from . import embedded

        return embedded.is_available()

    def generate(self, source: str, *, filename: str = "main.c", representation: str = "all") -> CpgResult:
        from . import embedded

        graphson = embedded.generate_cpg(source, filename=filename, representation=representation)
        return CpgResult(graphson, count_methods(graphson), self.name)


def joern_container_name() -> str:
    """Container the docker backend talks to (matches docker-compose.yml)."""
    username = os.getenv("USER") or os.getenv("USERNAME") or "user"
    return os.getenv("SSAT_JOERN_CONTAINER") or f"ssat-joern-{username}"


def run_joern_in_container(
    job_dir: Path,
    container_source: str,
    container_work_dir: str,
    *,
    container_name: str,
    representation: str = "all",
    export_format: str = "graphson",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Run joern-parse then joern-export inside the container; return GraphSON.

    Single implementation of the docker invocation. There used to be two -- an
    async one for single files and a sync one for the batch workers -- issuing
    the same two ``docker exec`` calls.
    """
    parse = subprocess.run(
        [
            "docker",
            "exec",
            "-w",
            container_work_dir,
            container_name,
            "/opt/joern/joern-cli/bin/joern-parse",
            container_source,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if parse.returncode != 0:
        raise RuntimeError(f"joern-parse failed: {parse.stderr}")
    if not (job_dir / "cpg.bin").exists():
        raise RuntimeError("cpg.bin not found after joern-parse")

    export = subprocess.run(
        [
            "docker",
            "exec",
            "-w",
            container_work_dir,
            container_name,
            "/opt/joern/joern-cli/bin/joern-export",
            f"--repr={representation}",
            f"--format={export_format}",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if export.returncode != 0:
        raise RuntimeError(f"joern-export failed: {export.stderr}")

    stdout = export.stdout.strip()
    if stdout.startswith("{"):
        try:
            parsed: Dict[str, Any] = json.loads(stdout)
            return parsed
        except json.JSONDecodeError:
            pass  # fall through to reading the output directory

    out_dir = job_dir / "out"
    if not out_dir.exists():
        raise RuntimeError("joern-export produced no output directory")
    json_files = sorted(out_dir.rglob("*.json"))
    if not json_files:
        raise RuntimeError("No JSON files found in joern-export output")

    merged: Dict[str, Any] = {}
    for json_file in json_files:
        data = json.loads(json_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged.update(data)
    return merged


#: Host side of the container's /workspace bind mount, relative to the repo
#: root. Must match the volume in docker-compose.yml.
WORKSPACE_SUBDIR = Path("artifacts") / "workspace"


def _workspace_dir() -> Path:
    """Host side of the container's /workspace bind mount."""
    override = os.getenv("SSAT_JOERN_WORKSPACE")
    if override:
        return Path(override)

    current = Path.cwd()
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current / WORKSPACE_SUBDIR
        current = current.parent
    return Path.cwd() / WORKSPACE_SUBDIR


class DockerBackend:
    """Joern in a container, driven with ``docker exec``."""

    name = "docker"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", joern_container_name()],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except OSError, subprocess.SubprocessError:
            return False
        return result.returncode == 0 and result.stdout.strip() == "true"

    def generate(self, source: str, *, filename: str = "main.c", representation: str = "all") -> CpgResult:
        workspace = _workspace_dir()
        workspace.mkdir(parents=True, exist_ok=True)

        job_id = uuid.uuid4().hex[:12]
        job_dir = workspace / f"job_{job_id}"
        job_source = job_dir / filename
        job_source.parent.mkdir(parents=True, exist_ok=True)
        job_source.write_text(source if source.endswith("\n") else source + "\n", encoding="utf-8")

        try:
            graphson = run_joern_in_container(
                job_dir,
                f"/workspace/job_{job_id}/{filename}",
                f"/workspace/job_{job_id}",
                container_name=joern_container_name(),
                representation=representation,
            )
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

        return CpgResult(graphson, count_methods(graphson), self.name)

    def generate_file(self, source_file: Path, *, representation: str = "all") -> CpgResult:
        """Generate from a file on disk, preserving its name."""
        return self.generate(
            source_file.read_text(encoding="utf-8", errors="replace"),
            filename=source_file.name,
            representation=representation,
        )


_BACKENDS: Dict[str, CpgBackend] = {
    EmbeddedBackend.name: EmbeddedBackend(),
    DockerBackend.name: DockerBackend(),
}

BACKEND_NAMES = tuple(_BACKENDS)


def get_backend(name: str) -> CpgBackend:
    """Look up a backend by name (``jpype`` or ``docker``)."""
    try:
        return _BACKENDS[name]
    except KeyError:
        raise ValueError(f"unknown CPG backend {name!r}; choose from {', '.join(BACKEND_NAMES)}") from None


def generate_cpg(
    source: str,
    *,
    backend: str = EmbeddedBackend.name,
    filename: str = "main.c",
    representation: str = "all",
) -> CpgResult:
    """Generate a CPG with the named backend."""
    return get_backend(backend).generate(source, filename=filename, representation=representation)


def write_temp_source(source: str, filename: str) -> Path:
    """Write source to a throwaway directory; caller removes the parent."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="ssat-cpg-"))
    path = tmp_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source if source.endswith("\n") else source + "\n", encoding="utf-8")
    return path
