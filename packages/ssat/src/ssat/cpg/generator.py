import json
import multiprocessing
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from .backends import EmbeddedBackend

SUPPORTED_EXTENSIONS = frozenset(
    {
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hxx",
        ".java",
    }
)


def is_supported_source_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _relative_source_path(src: Path, input_root: Path) -> Path:
    if input_root.is_file():
        return Path(src.name)
    try:
        rel_path = src.relative_to(input_root)
    except ValueError:
        return Path(src.name)
    return Path(src.name) if rel_path == Path(".") else rel_path


def _cpg_json_output_path(output_root: Path, rel_source_path: Path) -> Path:
    return output_root / rel_source_path.parent / f"{rel_source_path.name}.json"


def _worker_generate_one(
    source_file: str,
    input_root: str,
    output_root: str,
    representation: str,
    copy_source: bool = False,
) -> Dict[str, Any]:
    src = Path(source_file)
    out_root = Path(output_root)

    try:
        rel_path = _relative_source_path(src, Path(input_root))
        result = EmbeddedBackend().generate_file(src, representation=representation)
        output_file = _cpg_json_output_path(out_root, rel_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(result.graphson, indent=2), encoding="utf-8")

        if copy_source:
            source_copy = out_root / rel_path
            source_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, source_copy)

        return {"success": True, "file": source_file, "output": str(output_file)}

    except Exception as exc:  # noqa: BLE001 - reported per-file, never kills the batch
        return {"success": False, "file": source_file, "error": str(exc)}


def batch_generate_cpg(
    files: List[Path],
    input_root: Path,
    output_root: Path,
    workers: int = 4,
    representation: str = "all",
    copy_source: bool = False,
    progress_callback: Any = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    context = multiprocessing.get_context("spawn")

    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as executor:
        future_to_file = {
            executor.submit(
                _worker_generate_one,
                str(f),
                str(input_root),
                str(output_root),
                representation,
                copy_source,
            ): f
            for f in files
        }

        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            if progress_callback:
                progress_callback(result)

    return results
