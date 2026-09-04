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

#: Flags that silence the JVM's own startup warnings -- JPype's native `System.load`
#: and Scala's `sun.misc.Unsafe` use. They are printed before any Java we control
#: runs, so a flag is the only way to stop them. Passed with `ignoreUnrecognized`
#: because the second is JDK 23+; see :func:`_start_jvm`.
_QUIET_JVM_FLAGS = ("--enable-native-access=ALL-UNNAMED", "--sun-misc-unsafe-memory-access=allow")

_lock = threading.Lock()  # serialise generation + JVM startup
_started = False
_JoernParse: Any = None
_JoernExport: Any = None
_JString: Any = None
_java_output: Any = None  # the JVM's stdout/stderr, diverted; see _install_java_output_capture


def joern_home() -> Path:
    return Path(os.getenv("JOERN_HOME", _DEFAULT_JOERN_HOME))


def _classpath() -> List[str]:
    lib = joern_home() / "lib"
    jars = glob.glob(str(lib / "*.jar"))
    if not jars:
        raise RuntimeError(f"No Joern JARs found under {lib}. Set JOERN_HOME to a joern-cli install.")
    return jars


def _quiet_joern_logging() -> None:
    """Ask Joern for WARN-level logs, before the JVM reads its configuration.

    Joern's ``log4j2.xml`` declares ``<Root level="${env:SL_LOGGING_LEVEL:-info}">``,
    so this environment variable is the supported knob and ``info`` is why ~95
    lines per source file used to shred the CLI's progress bar. It must be set
    before ``startJVM``: Log4j2 resolves the level once, when it configures.

    Two earlier attempts are worth not repeating. Reaching for
    ``ch.qos.logback.classic.Level`` never worked at all -- Joern binds SLF4J to
    Log4j2, so the class is absent and every call threw into a bare ``except``.
    Its replacement, ``Configurator.setRootLevel``, *did* work but segfaulted the
    interpreter under pytest, whose faulthandler intercepts the SIGSEGV the JVM
    raises for its own internal null checks. An environment variable read at
    startup touches none of that machinery.

    An explicit ``SL_LOGGING_LEVEL`` from the caller wins, so a noisy run is
    still one variable away.
    """
    os.environ.setdefault("SL_LOGGING_LEVEL", "warn")


def _install_java_output_capture(jpype: Any) -> None:
    """Point the JVM's ``System.out``/``System.err`` at a buffer we own, for good.

    Installed once, at startup, and never restored -- because Log4j2's
    ConsoleAppender resolves ``SYSTEM_OUT`` when it *configures*, which happens
    lazily on Joern's first log call. Swapping the streams per file instead
    bound the appender to whichever buffer happened to be installed first: that
    one file captured every log record in the run, every later file captured
    none, and the first buffer grew for the lifetime of the JVM. One permanent
    sink, reset per file, gets each file its own output and bounds the memory.
    """
    global _java_output
    _java_output = jpype.JClass("java.io.ByteArrayOutputStream")()
    sink = jpype.JClass("java.io.PrintStream")(_java_output, True)
    system = jpype.JClass("java.lang.System")
    system.setOut(sink)
    system.setErr(sink)


@contextlib.contextmanager
def _captured_java_output() -> Iterator[Any]:
    """Collect what Joern writes during the block, isolated from other files.

    Catches both halves of Joern's output: the progress banners ("Parsing code
    at:", "[+] Running language frontend", the ``====`` rule), which are plain
    ``System.out.println`` and no log level can silence, and the log records
    themselves, since the appender writes to this same sink.

    Callers hold ``_lock``, so the reset is never concurrent with another file.
    """
    if _java_output is None:  # capture unavailable; nothing to isolate
        yield None
        return
    _java_output.reset()
    yield _java_output


def _ensure_jvm() -> None:
    """Start the embedded JVM once and cache the Joern entrypoint classes."""
    global _started, _JoernParse, _JoernExport, _JString
    if _started:
        return
    import jpype  # imported lazily so the package loads without a JVM

    if not jpype.isJVMStarted():
        _start_jvm(jpype)
    _install_java_output_capture(jpype)
    _JoernParse = jpype.JClass("io.joern.joerncli.JoernParse")
    _JoernExport = jpype.JClass("io.joern.joerncli.JoernExport")
    _JString = jpype.JClass("java.lang.String")
    _started = True


def _start_jvm(jpype: Any) -> None:
    """Start the JVM with its own startup warnings suppressed.

    ``ignoreUnrecognized`` is what makes the flags safe to pass unconditionally:
    ``--sun-misc-unsafe-memory-access`` only exists from JDK 23, and a JDK that
    does not know a flag *aborts startup* over it. Catching that and retrying
    without the flags is not an option -- a failed ``startJVM`` leaves JPype
    unable to find its own support library, so the second attempt dies with a
    misleading "Can't find org.jpype.jar". Letting the JVM skip what it does not
    recognise keeps one attempt, and an older JDK simply keeps its warnings.
    """
    _quiet_joern_logging()
    _disable_jvm_destroy_on_exit()
    jpype.startJVM(
        *_QUIET_JVM_FLAGS,
        classpath=_classpath(),
        convertStrings=True,
        ignoreUnrecognized=True,
    )


def _disable_jvm_destroy_on_exit() -> None:
    """Skip ``DestroyJavaVM`` in JPype's atexit hook; the process is ending anyway.

    JPype's ``_JTerminate`` segfaults during interpreter shutdown -- its own
    source warns it "can experience a crash if a Java thread is waiting for the
    GIL". Quieting Joern is what exposed it here: with the root logger at
    ``info`` the appender keeps working and teardown happens to survive, while
    at ``warn`` the suite passed and then died with signal 11, turning a green
    run into exit 139.

    ``destroy_jvm`` is JPype's own knob for this and is narrower than
    ``onexit``: the shutdown still runs, only the blocking ``DestroyJavaVM``
    call is skipped. Nothing needs it -- the OS reclaims the JVM with the rest
    of the process.
    """
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
    """Append Joern's captured banners to an error message, if it wrote any."""
    banner = _joern_text(buffer)
    return f"{message}\n{banner}" if banner else message


def _joern_text(buffer: Any) -> str:
    """The text Joern wrote while its streams were diverted."""
    if buffer is None:
        return ""
    return str(buffer.toString()).strip()


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
            # `with` outside `try` so a failure to install the capture cannot
            # leave `joern_output` unbound in the handler that reads it.
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
                    # Joern's banners are worth reading only when something went
                    # wrong, so they ride along with the failure rather than
                    # scrolling past the progress bar on every successful file.
                    # The read is inside the capture on purpose: Joern's `main`
                    # can print its complaint and return normally, so "produced
                    # no JSON output" is often the *only* signal there is, and
                    # the reason for it is in the text we just captured.
                    detail = _with_joern_output(str(exc), joern_output)
                    raise RuntimeError(f"embedded Joern generation failed: {detail}") from exc
                logger.debug("joern output for %s:\n%s", filename, _joern_text(joern_output))
            return graphson
        finally:
            shutil.rmtree(work, ignore_errors=True)


def is_available() -> bool:
    """True if a Joern install (JARs) is present for embedded generation."""
    try:
        return bool(_classpath())
    except Exception:  # noqa: BLE001
        return False
