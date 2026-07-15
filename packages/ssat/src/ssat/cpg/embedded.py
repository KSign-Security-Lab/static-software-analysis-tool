"""In-process CPG generation via an embedded JVM (JPype), no Docker/subprocess.

Loads Joern's JARs into a JVM running *inside* the Python process and calls
Joern's own ``JoernParse`` / ``JoernExport`` entrypoints. Produces the exact same
GraphSON that ``joern-export`` does, so ``ssat.f2a`` and the web consume it
unchanged.

The JVM is started once per process and reused; generation is serialised with a
lock (Joern's parse/export are not concurrency-safe). Point at a Joern install
with ``JOERN_HOME`` (defaults to ``/usr/bin/joern/joern-cli``); a JDK must be on
the host.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List

_DEFAULT_JOERN_HOME = "/usr/bin/joern/joern-cli"

_lock = threading.Lock()  # serialise generation + JVM startup
_started = False
_JoernParse: Any = None
_JoernExport: Any = None
_JString: Any = None


def joern_home() -> Path:
    return Path(os.getenv("JOERN_HOME", _DEFAULT_JOERN_HOME))


def _classpath() -> List[str]:
    lib = joern_home() / "lib"
    jars = glob.glob(str(lib / "*.jar"))
    if not jars:
        raise RuntimeError(
            f"No Joern JARs found under {lib}. Set JOERN_HOME to a joern-cli install."
        )
    return jars


def _quiet_logging(jpype: Any) -> None:
    """Drop Joern's INFO logback chatter to WARN."""
    try:
        factory = jpype.JClass("org.slf4j.LoggerFactory")
        root = factory.getLogger("ROOT")
        level = jpype.JClass("ch.qos.logback.classic.Level")
        root.setLevel(level.WARN)
    except Exception:  # noqa: BLE001 - logging backend may differ; non-fatal
        pass


def _ensure_jvm() -> None:
    """Start the embedded JVM once and cache the Joern entrypoint classes."""
    global _started, _JoernParse, _JoernExport, _JString
    if _started:
        return
    import jpype  # imported lazily so the package loads without a JVM

    if not jpype.isJVMStarted():
        jpype.startJVM(classpath=_classpath(), convertStrings=True)
    _quiet_logging(jpype)
    _JoernParse = jpype.JClass("io.joern.joerncli.JoernParse")
    _JoernExport = jpype.JClass("io.joern.joerncli.JoernExport")
    _JString = jpype.JClass("java.lang.String")
    _started = True


def _jargs(*args: str) -> Any:
    import jpype

    arr = jpype.JArray(_JString)(len(args))
    for i, a in enumerate(args):
        arr[i] = a
    return arr


def _attach_thread() -> None:
    import jpype

    if not jpype.isThreadAttachedToJVM():
        jpype.attachThreadToJVM()


def _read_graphson(out_dir: Path) -> Dict[str, Any]:
    files = sorted(out_dir.rglob("*.json"))
    if not files:
        raise RuntimeError("joern-export produced no JSON output")
    merged: Dict[str, Any] = {}
    for jf in files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged.update(data)
    return merged


def generate_cpg(source: str, filename: str = "main.c", representation: str = "all") -> Dict[str, Any]:
    """Generate a CPG GraphSON dict from source, entirely in-process.

    Raises RuntimeError on parse/export failure (never terminates the process).
    """
    text = source if source.endswith("\n") else source + "\n"
    with _lock:
        _ensure_jvm()
        _attach_thread()
        work = Path(tempfile.mkdtemp(prefix="ssat-embed-"))
        try:
            src = work / filename
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(text, encoding="utf-8")
            cpg_bin = work / "cpg.bin"
            out_dir = work / "out"
            try:
                _JoernParse.main(_jargs(str(src), "-o", str(cpg_bin)))
                if not cpg_bin.exists():
                    raise RuntimeError("joern-parse did not produce cpg.bin")
                _JoernExport.main(
                    _jargs(str(cpg_bin), "--repr", representation, "--format", "graphson", "-o", str(out_dir))
                )
            except Exception as exc:  # noqa: BLE001 - surface as a clean error
                raise RuntimeError(f"embedded Joern generation failed: {exc}") from exc
            return _read_graphson(out_dir)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def is_available() -> bool:
    """True if a Joern install (JARs) is present for embedded generation."""
    try:
        return bool(_classpath())
    except Exception:  # noqa: BLE001
        return False
