from __future__ import annotations

import contextlib
import glob
import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Iterator, List

logger = logging.getLogger(__name__)
_DEFAULT_JOERN_HOME = "/usr/bin/joern/joern-cli"
_QUIET_JVM_FLAGS = ("--enable-native-access=ALL-UNNAMED", "--sun-misc-unsafe-memory-access=allow")
_lock = threading.Lock()
_started = False
_JoernParse: Any = None
_JoernExport: Any = None
_JString: Any = None
_java_output: Any = None


def joern_home() -> Path:
    return Path(os.getenv("JOERN_HOME", _DEFAULT_JOERN_HOME))


def _classpath() -> List[str]:
    lib = joern_home() / "lib"
    jars = glob.glob(str(lib / "*.jar"))
    if not jars:
        raise RuntimeError(f"No Joern JARs found under {lib}. Set JOERN_HOME to a joern-cli install.")
    return jars


def _quiet_joern_logging() -> None:
    os.environ.setdefault("SL_LOGGING_LEVEL", "warn")


def _install_java_output_capture(jpype: Any) -> None:
    global _java_output
    _java_output = jpype.JClass("java.io.ByteArrayOutputStream")()
    sink = jpype.JClass("java.io.PrintStream")(_java_output, True)
    system = jpype.JClass("java.lang.System")
    system.setOut(sink)
    system.setErr(sink)


@contextlib.contextmanager
def _captured_java_output() -> Iterator[Any]:
    if _java_output is None:
        yield None
        return
    _java_output.reset()
    yield _java_output


def _ensure_jvm() -> None:
    global _started, _JoernParse, _JoernExport, _JString
    if _started:
        return
    import jpype

    if not jpype.isJVMStarted():
        _start_jvm(jpype)
    _install_java_output_capture(jpype)
    _JoernParse = jpype.JClass("io.joern.joerncli.JoernParse")
    _JoernExport = jpype.JClass("io.joern.joerncli.JoernExport")
    _JString = jpype.JClass("java.lang.String")
    _started = True


def _start_jvm(jpype: Any) -> None:
    _quiet_joern_logging()
    _disable_jvm_destroy_on_exit()
    jpype.startJVM(
        *_QUIET_JVM_FLAGS,
        classpath=_classpath(),
        convertStrings=True,
        ignoreUnrecognized=True,
    )


def _disable_jvm_destroy_on_exit() -> None:
    import jpype.config

    jpype.config.destroy_jvm = False


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


def _with_joern_output(message: str, buffer: Any) -> str:
    banner = _joern_text(buffer)
    return f"{message}\n{banner}" if banner else message


def _joern_text(buffer: Any) -> str:
    if buffer is None:
        return ""
    return str(buffer.toString()).strip()


def generate_cpg(source: str, filename: str = "main.c", representation: str = "all") -> Dict[str, Any]:
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
            with _captured_java_output() as joern_output:
                try:
                    _JoernParse.main(_jargs(str(src), "-o", str(cpg_bin)))
                    if not cpg_bin.exists():
                        raise RuntimeError("joern-parse did not produce cpg.bin")
                    _JoernExport.main(
                        _jargs(str(cpg_bin), "--repr", representation, "--format", "graphson", "-o", str(out_dir))
                    )
                    graphson = _read_graphson(out_dir)
                except Exception as exc:  # noqa: BLE001 - surface as a clean error
                    detail = _with_joern_output(str(exc), joern_output)
                    raise RuntimeError(f"embedded Joern generation failed: {detail}") from exc
                logger.debug("joern output for %s:\n%s", filename, _joern_text(joern_output))
            return graphson
        finally:
            shutil.rmtree(work, ignore_errors=True)


def is_available() -> bool:
    try:
        return bool(_classpath())
    except Exception:  # noqa: BLE001
        return False
