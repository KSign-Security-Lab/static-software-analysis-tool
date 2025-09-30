from typing import Any, Dict

from deepdiff import DeepDiff


def check_diff(dataA: Dict[str, Any], dataB: Dict[str, Any]) -> bool:
    diff = DeepDiff(dataA, dataB, ignore_order=True, significant_digits=6)
    print(diff)  # {} means no differences
    return diff == {}
