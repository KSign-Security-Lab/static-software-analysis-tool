import glob
import json
import os
from datetime import datetime
from typing import Any, Dict, List

DFG_NODE_SCHEMA = {
    "sid": int,
    # "orig_id": int,
    "feat": {
        "node_type_id": str,
        "in_degree_dfg": int,
        "out_degree_dfg": int,
        "def_count": int,
        "use_count": int,
        "is_buffer_access": int,
        "is_sink_assign": int,
        "is_sink_call_unbounded": int,
        "is_sink_call_bounded": int,
        "call_dst_indexed": int,
        "call_len_linked_to_dst": int,
        "call_size_nonconst": int,
        "call_danger_unbounded": int,
    },
    # "debug": {
    #     "code": str,
    #     "def_vars": [str],
    #     "use_vars": [str],
    # },
}

DFG_EDGE_SCHEMA = {
    "feat": {
        "flow_id": int,
        "guard_kind": int,
        "has_lower_guard": int,
        "has_upper_guard": int,
        "upper_guard_norm": float,
    },
    # "debug": {
    #     "var_key": str,
    # },
}

DFG_SCHEMA = {
    "nodes": [DFG_NODE_SCHEMA],
    # Enable to compare edges as list of tuples [src, dst, payload]
    "edges_dfg": [[int, int, DFG_EDGE_SCHEMA]],
}


def load_json(file_path: str) -> Dict[str, Any]:
    """Load JSON file with error handling."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")


def compare_value(value1: Any, value2: Any, path: str = "") -> bool:
    """Compare two values."""
    if value1 != value2:
        raise ValueError(f"Value mismatch at {path}: {value1} != {value2}")
    return True


def compare_by_schema(obj1: Any, obj2: Any, schema: Any, path: str = "") -> bool:
    # Dict schema
    if isinstance(schema, dict):
        if not isinstance(obj1, dict) or not isinstance(obj2, dict):
            raise ValueError(f"Type mismatch at {path}: expected dict")
        for key, sub_schema in schema.items():
            if key not in obj1 or key not in obj2:
                raise ValueError(f"Key '{key}' missing at {path}")
            sub_path = f"{path}.{key}" if path else key
            compare_by_schema(obj1[key], obj2[key], sub_schema, sub_path)
        return True

    # List schema
    if isinstance(schema, list):
        if not isinstance(obj1, list) or not isinstance(obj2, list):
            raise ValueError(f"Type mismatch at {path}: expected list")
        if len(schema) == 1:
            # Homogeneous list: all items follow the single inner schema
            inner_schema = schema[0]
            if len(obj1) != len(obj2):
                raise ValueError(f"List length mismatch at {path}: {len(obj1)} != {len(obj2)}")
            for idx, (a, b) in enumerate(zip(obj1, obj2)):
                sub_path = f"{path}[{idx}]"
                compare_by_schema(a, b, inner_schema, sub_path)
            return True
        else:
            # Tuple-like schema for each element of outer list
            # Example schema: [[int, int, DFG_EDGE_SCHEMA]]
            tuple_schema = schema
            if len(obj1) != len(obj2):
                raise ValueError(f"List length mismatch at {path}: {len(obj1)} != {len(obj2)}")
            for i, (item1, item2) in enumerate(zip(obj1, obj2)):
                sub_path = f"{path}[{i}]"
                if not isinstance(item1, (list, tuple)) or not isinstance(item2, (list, tuple)):
                    raise ValueError(f"Type mismatch at {sub_path}: expected tuple-like list")
                if len(item1) != len(tuple_schema) or len(item2) != len(tuple_schema):
                    raise ValueError(
                        f"Tuple size mismatch at {sub_path}: {len(item1)} != {len(tuple_schema)} or {len(item2)} != {len(tuple_schema)}"
                    )
                for j, sub_schema in enumerate(tuple_schema):
                    compare_by_schema(item1[j], item2[j], sub_schema, f"{sub_path}[{j}]")
            return True

    # Primitive schema
    return compare_value(obj1, obj2, path)


def get_enabled_keys() -> List[str]:
    return list(DFG_SCHEMA.keys())


def compare_dfg(dfg1: Dict[str, Any], dfg2: Dict[str, Any]) -> bool:
    """Compare two DFG results strictly by DFG_SCHEMA."""
    print("Comparing DFG structures (schema-driven)...")
    # Only compare keys defined in schema
    for key, sub_schema in DFG_SCHEMA.items():
        if key not in dfg1 or key not in dfg2:
            raise ValueError(f"Key '{key}' not found in both DFGs")
        compare_by_schema(dfg1[key], dfg2[key], sub_schema, key)
    return True


def get_file_pairs(dir1: str, dir2: str) -> List[tuple[str, str]]:
    """Get matching file pairs from two directories."""
    files1 = sorted(glob.glob(os.path.join(dir1, "*.json")))
    files2 = sorted(glob.glob(os.path.join(dir2, "*.json")))

    files2_map = {os.path.basename(f): f for f in files2}

    pairs = []
    for file1 in files1:
        basename = os.path.basename(file1)
        if basename in files2_map:
            pairs.append((file1, files2_map[basename]))
        else:
            print(f"Warning: No matching file for {basename} in {dir2}")

    return pairs


def analyze_differences(dfg1: Dict[str, Any], dfg2: Dict[str, Any], file1: str, file2: str) -> Dict[str, Any]:
    """Analyze specific differences between two DFG results (schema-driven)."""
    analysis: Dict[str, Any] = {
        "file1": file1,
        "file2": file2,
        "structure_differences": [],
        "size_differences": {},
    }

    enabled = set(get_enabled_keys())

    # Structure differences limited to enabled keys
    keys1 = set(dfg1.keys()) & enabled
    keys2 = set(dfg2.keys()) & enabled

    if keys1 != keys2:
        analysis["structure_differences"].append(
            {
                "type": "missing_keys",
                "dfg1_only": list(keys1 - keys2),
                "dfg2_only": list(keys2 - keys1),
            }
        )

    # Size differences only for list keys in schema
    for key in keys1 & keys2:
        schema_entry = DFG_SCHEMA.get(key)
        if isinstance(schema_entry, list) and isinstance(dfg1.get(key), list) and isinstance(dfg2.get(key), list):
            len1, len2 = len(dfg1[key]), len(dfg2[key])
            if len1 != len2:
                analysis["size_differences"][key] = {
                    "dfg1_length": len1,
                    "dfg2_length": len2,
                    "difference": len1 - len2,
                }

    return analysis


def save_failure_report(failure_details: List[Dict], error_types: Dict, dfg1_dir: str, dfg2_dir: str) -> None:
    """Save detailed failure report to a JSON file for debugging."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"comparison_failure_report_{timestamp}.json"

    report = {
        "timestamp": timestamp,
        "directories": {"dfg1_dir": dfg1_dir, "dfg2_dir": dfg2_dir},
        "summary": {"total_failures": len(failure_details), "error_types": error_types},
        "failures": failure_details,
    }

    try:
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"📄 Detailed failure report saved to: {report_file}")
    except Exception as e:
        print(f"⚠️  Could not save failure report: {e}")


def main(dfg1_dir: str, dfg2_dir: str) -> None:
    """Compare DFG results from two directories."""
    print("Comparing DFG results:")
    print(f"  Directory 1: {dfg1_dir}")
    print(f"  Directory 2: {dfg2_dir}")
    print()

    if not os.path.exists(dfg1_dir):
        raise FileNotFoundError(f"Directory not found: {dfg1_dir}")
    if not os.path.exists(dfg2_dir):
        raise FileNotFoundError(f"Directory not found: {dfg2_dir}")

    file_pairs = get_file_pairs(dfg1_dir, dfg2_dir)

    if not file_pairs:
        print("No matching files found to compare.")
        return

    print(f"Found {len(file_pairs)} file pairs to compare.")
    print()

    successful_comparisons = 0
    failed_comparisons = 0
    failure_details: List[Dict[str, Any]] = []
    error_types: Dict[str, int] = {}
    file_size_stats = {"dfg1": [], "dfg2": []}

    enabled = set(get_enabled_keys())
    edges_enabled = "edges_dfg" in enabled

    for i, (dfg1_file, dfg2_file) in enumerate(file_pairs, 1):
        dfg1 = None
        dfg2 = None
        try:
            print(f"[{i}/{len(file_pairs)}] Comparing {os.path.basename(dfg1_file)}...")

            file1 = load_json(dfg1_file)
            file2 = load_json(dfg2_file)

            if "dfg_result" not in file1:
                raise ValueError(f"Missing 'dfg_result' key in {dfg1_file}")
            if "dfg_result" not in file2:
                raise ValueError(f"Missing 'dfg_result' key in {dfg2_file}")

            dfg1 = file1["dfg_result"]
            dfg2 = file2["dfg_result"]

            # Collect size statistics (schema-driven)
            file_size_stats["dfg1"].append(
                {
                    "file": os.path.basename(dfg1_file),
                    "nodes": len(dfg1.get("nodes", [])),
                    "edges": len(dfg1.get("edges_dfg", [])) if edges_enabled else 0,
                    "file_size": os.path.getsize(dfg1_file),
                }
            )
            file_size_stats["dfg2"].append(
                {
                    "file": os.path.basename(dfg2_file),
                    "nodes": len(dfg2.get("nodes", [])),
                    "edges": len(dfg2.get("edges_dfg", [])) if edges_enabled else 0,
                    "file_size": os.path.getsize(dfg2_file),
                }
            )

            # Compare DFG results (schema-driven)
            compare_dfg(dfg1, dfg2)

            print("  ✓ Files are identical")
            successful_comparisons += 1

        except Exception as e:
            error_type = type(e).__name__
            error_types[error_type] = error_types.get(error_type, 0) + 1

            analysis = None
            if dfg1 is not None and dfg2 is not None:
                try:
                    analysis = analyze_differences(
                        dfg1,
                        dfg2,
                        os.path.basename(dfg1_file),
                        os.path.basename(dfg2_file),
                    )
                except Exception:
                    analysis = None

            failure_details.append(
                {
                    "file": os.path.basename(dfg1_file),
                    "error_type": error_type,
                    "error_message": str(e),
                    "dfg1_nodes": (len(dfg1.get("nodes", [])) if dfg1 is not None else 0),
                    "dfg2_nodes": (len(dfg2.get("nodes", [])) if dfg2 is not None else 0),
                    "dfg1_edges": (len(dfg1.get("edges_dfg", [])) if (dfg1 is not None and edges_enabled) else 0),
                    "dfg2_edges": (len(dfg2.get("edges_dfg", [])) if (dfg2 is not None and edges_enabled) else 0),
                    "analysis": analysis,
                }
            )

            print(f"  ✗ Comparison failed: {e}")
            if analysis and analysis.get("size_differences"):
                print(f"    Size differences: {analysis['size_differences']}")
            failed_comparisons += 1

        print()

    print("=" * 60)
    print("DETAILED COMPARISON SUMMARY")
    print("=" * 60)
    print(f"Total file pairs: {len(file_pairs)}")
    print(f"Successful comparisons: {successful_comparisons}")
    print(f"Failed comparisons: {failed_comparisons}")
    print(f"Success rate: {(successful_comparisons / len(file_pairs)) * 100:.1f}%")
    print()

    if failed_comparisons > 0:
        print("ERROR TYPE BREAKDOWN:")
        print("-" * 30)
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            print(f"  {error_type}: {count} failures")
        print()

        print("FAILURE DETAILS:")
        print("-" * 30)
        for i, failure in enumerate(failure_details, 1):
            print(f"{i:2d}. {failure['file']}")
            print(f"    Error: {failure['error_type']}: {failure['error_message']}")
            print(f"    DFG1: {failure['dfg1_nodes']} nodes, {failure['dfg1_edges']} edges")
            print(f"    DFG2: {failure['dfg2_nodes']} nodes, {failure['dfg2_edges']} edges")

            if failure.get("analysis"):
                analysis = failure["analysis"]
                if analysis.get("size_differences"):
                    print("    Size differences:")
                    for key, diff in analysis["size_differences"].items():
                        print(
                            f"      {key}: DFG1={diff['dfg1_length']}, DFG2={diff['dfg2_length']} (diff: {diff['difference']:+d})"
                        )

                if analysis.get("structure_differences"):
                    print("    Structure differences:")
                    for struct_diff in analysis["structure_differences"]:
                        if struct_diff["dfg1_only"]:
                            print(f"      DFG1 only: {struct_diff['dfg1_only']}")
                        if struct_diff["dfg2_only"]:
                            print(f"      DFG2 only: {struct_diff['dfg2_only']}")
            print()

    print("FILE SIZE STATISTICS:")
    print("-" * 30)
    dfg1_stats = file_size_stats["dfg1"]
    dfg2_stats = file_size_stats["dfg2"]

    if dfg1_stats:
        dfg1_avg_nodes = sum(s["nodes"] for s in dfg1_stats) / len(dfg1_stats)
        dfg1_avg_edges = sum(s["edges"] for s in dfg1_stats) / len(dfg1_stats)
        dfg1_avg_size = sum(s["file_size"] for s in dfg1_stats) / len(dfg1_stats)

        print("DFG1 (Directory 1):")
        print(f"  Average nodes: {dfg1_avg_nodes:.1f}")
        print(f"  Average edges: {dfg1_avg_edges:.1f}")
        print(f"  Average file size: {dfg1_avg_size:.0f} bytes")

    if dfg2_stats:
        dfg2_avg_nodes = sum(s["nodes"] for s in dfg2_stats) / len(dfg2_stats)
        dfg2_avg_edges = sum(s["edges"] for s in dfg2_stats) / len(dfg2_stats)
        dfg2_avg_size = sum(s["file_size"] for s in dfg2_stats) / len(dfg2_stats)

        print("DFG2 (Directory 2):")
        print(f"  Average nodes: {dfg2_avg_nodes:.1f}")
        print(f"  Average edges: {dfg2_avg_edges:.1f}")
        print(f"  Average file size: {dfg2_avg_size:.0f} bytes")

    print()

    if failed_comparisons == 0:
        print("🎉 All comparisons passed!")
    else:
        print(f"⚠️  {failed_comparisons} comparison(s) failed.")
        print("\nTo debug specific failures, check the failure details above.")
        save_failure_report(failure_details, error_types, dfg1_dir, dfg2_dir)


if __name__ == "__main__":
    dfg1_dir = "../../data/temp/full-new"
    dfg2_dir = "../../data/temp/full-legacy"

    main(dfg1_dir, dfg2_dir)
