#!/usr/bin/env python3
# Stream MANY JSON/JSONL files from a directory (recursively),
# assign each example to a split deterministically, and write sharded JSONL.

import hashlib
import json
import os
import pathlib
from collections import Counter, defaultdict

from tqdm import tqdm

# ===== CONFIG (edit these) =========================================
INPUT_DIR = "../../data/test/121_full"  # directory with *.json / *.jsonl (recurses)
OUTPUT_DIR = "../../data/v2/data"  # where shards go
TARGET_MB = 200  # approx shard size per file
SPLITS = (0.8, 0.1, 0.1)  # train/val/test (must sum to 1.0)
LABEL_KEY = "label"  # target field (if present in object)
KEEP = ["file", "ast_result", "dfg_result"]  # fields to carry forward
REQUIRE_ONE_OF = ["ast_result", "dfg_result"]  # at least one must exist to keep example
CLASS_NAMES = ["safe", "vulnerable"]  # docs only; output label stays int 0/1
LOWER_NAME_FOR_LABEL = True  # case-insensitive filename label derivation
# ===================================================================


def is_jsonl_file(path: str) -> bool:
    """Sniff first non-space char; '[' or '{' => JSON (array or single object); else assume JSONL."""
    with open(path, "rb") as f:
        while True:
            ch = f.read(1)
            if not ch:
                return False
            if ch in b" \t\r\n":
                continue
            return ch not in b"[{"


def iter_objects_from_file(path: str):
    """Yield dict objects from a JSONL file (one per line) OR a JSON file (list or single object)."""
    if is_jsonl_file(path):
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"JSON decode error in {path} line {line_num}: {e}"
                    ) from e
                if isinstance(obj, dict):
                    yield obj
    else:
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"JSON decode error in {path}: {e}") from e
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for obj in data:
                if isinstance(obj, dict):
                    yield obj


def derive_label_from_filename(filename: str):
    """Derive label from filename: *_bad* => 1 (vulnerable), *_good* => 0 (safe)."""
    name = filename.lower() if LOWER_NAME_FOR_LABEL else filename
    if "_bad" in name:
        return 1
    if "_good" in name:
        return 0
    return None


def coerce_label(x):
    """Coerce various label types to int {0,1}. Return None if invalid."""
    if isinstance(x, bool):
        return int(x)
    try:
        v = int(x)
    except Exception:
        return None
    return v if v in (0, 1) else None


def has_required_inputs(record: dict) -> bool:
    """Require at least one meaningful input field so we don't keep label-only rows."""
    return any((k in record) for k in REQUIRE_ONE_OF)


def assign_split(key_str: str) -> str:
    """Deterministic split using md5(key) → [0,1)."""
    h = hashlib.md5(key_str.encode("utf-8")).digest()
    v = int.from_bytes(h[:8], "big") / 2**64
    a, b, _ = SPLITS
    return "train" if v < a else ("validation" if v < a + b else "test")


class ShardWriter:
    def __init__(self, split: str):
        self.split = split
        self.dir = os.path.join(OUTPUT_DIR, split)
        os.makedirs(self.dir, exist_ok=True)
        self.shard_idx = 0
        self.cur_bytes = 0
        self.f = self._open_new()

    def _open_new(self):
        path = os.path.join(self.dir, f"{self.split}-{self.shard_idx:05d}.jsonl")
        self.shard_idx += 1
        self.cur_bytes = 0
        return open(path, "w", encoding="utf-8")

    def write(self, obj: dict):
        s = json.dumps(obj, ensure_ascii=False) + "\n"
        b = s.encode("utf-8")
        self.f.write(s)
        self.cur_bytes += len(b)
        if self.cur_bytes >= TARGET_MB * 1024 * 1024:
            self.f.close()
            self.f = self._open_new()

    def close(self):
        if self.f:
            self.f.close()


def main():
    writers = {split: ShardWriter(split) for split in ["train", "validation", "test"]}

    # stats
    total_seen = 0
    total_kept = 0
    split_counts = Counter()
    label_counts_by_split = defaultdict(Counter)

    # First, count total files for progress bar
    all_files = []
    for root, _, files in os.walk(INPUT_DIR):
        for name in files:
            if name.endswith(".json") or name.endswith(".jsonl"):
                all_files.append(os.path.join(root, name))

    print(f"Processing {len(all_files)} files...")

    with tqdm(total=len(all_files), desc="Processing files", unit="file") as pbar:
        for root, _, files in os.walk(INPUT_DIR):
            for name in files:
                if not (name.endswith(".json") or name.endswith(".jsonl")):
                    continue

                path = os.path.join(root, name)
                # default/derived label from filename (overridden by in-object label if present)
                file_lab = derive_label_from_filename(name)

                local_idx = 0
                rel_path = os.path.relpath(path, INPUT_DIR)

                for obj in iter_objects_from_file(path):
                    total_seen += 1

                    # pick label: object wins if present and valid; else filename-derived
                    lab = None
                    if LABEL_KEY in obj:
                        lab = coerce_label(obj[LABEL_KEY])
                    if lab is None:
                        lab = file_lab
                    if lab is None:
                        local_idx += 1
                        continue  # skip unlabeled

                    # build output
                    out: dict = {"label": lab}

                    # always preserve a `file` field (relative path) for provenance
                    if "file" in obj and isinstance(obj["file"], str) and obj["file"]:
                        out["file"] = obj["file"]
                    else:
                        out["file"] = rel_path

                    # copy other kept fields if present
                    for k in KEEP:
                        if k == "file":  # already handled
                            continue
                        if k in obj:
                            # Convert complex objects to JSON strings for Hugging Face compatibility
                            if isinstance(obj[k], (dict, list)):
                                out[k] = json.dumps(obj[k], ensure_ascii=False)
                            else:
                                out[k] = obj[k]

                    # skip if no required inputs
                    if not has_required_inputs(out):
                        local_idx += 1
                        continue

                    # deterministic split by path + local index + label
                    key = f"{rel_path}::{local_idx}::{lab}"
                    split = assign_split(key)

                    writers[split].write(out)
                    total_kept += 1
                    split_counts[split] += 1
                    label_counts_by_split[split][lab] += 1

                    local_idx += 1

                # Update progress bar with current stats
                pbar.set_postfix(
                    {
                        "seen": total_seen,
                        "kept": total_kept,
                        "train": split_counts["train"],
                        "val": split_counts["validation"],
                        "test": split_counts["test"],
                    }
                )
                pbar.update(1)

    for w in writers.values():
        w.close()

    # dataset card
    repo_root = pathlib.Path(OUTPUT_DIR).parent
    readme = repo_root / "README.md"
    if not readme.exists():
        readme.write_text(
            f"""---
dataset_info:
  features:
    - name: file
      dtype: string
    - name: label
      dtype:
        class_label:
          names: {CLASS_NAMES}
    - name: ast_result
      dtype: string
    - name: dfg_result
      dtype: string
license: apache-2.0
tags: [security, cwe, jsonl, streaming]
task_categories: [text-classification]
configs:
  - config_name: default
    data_files:
      - data/train/*.jsonl
      - data/validation/*.jsonl
      - data/test/*.jsonl
---

# CWE Vulnerability Dataset (Directory Ingest)

- Binary label: 0={CLASS_NAMES[0]}, 1={CLASS_NAMES[1]}
- Examples gathered from {INPUT_DIR}; deterministic split via MD5(path,line_index,label).
- Each example includes `file` (relative path), plus `ast_result` / `dfg_result` if present.
""",
            encoding="utf-8",
        )

    # Pretty stats
    print(f"\nDone. Total seen: {total_seen}, kept: {total_kept}")
    for split in ["train", "validation", "test"]:
        n = split_counts[split]
        if n == 0:
            print(f"- {split}: 0")
            continue
        c0 = label_counts_by_split[split][0]
        c1 = label_counts_by_split[split][1]
        p0 = (c0 / n) * 100
        p1 = (c1 / n) * 100
        print(
            f"- {split}: {n}  |  label 0: {c0} ({p0:.1f}%)  label 1: {c1} ({p1:.1f}%)"
        )
    print(f"Output → {repo_root} (README.md + data/ shards)")


if __name__ == "__main__":
    main()
