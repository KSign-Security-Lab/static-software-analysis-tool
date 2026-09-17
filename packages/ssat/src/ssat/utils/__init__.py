import json
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

from .tree_to_text import TreeToText as TreeToText


def multiprocess(func: Callable[[Any], Any], args: List[Any], num_processes: int) -> List[Any]:
    with Pool(num_processes) as p:
        return p.map(func, args)


def read_json(file_path: str | Path) -> Dict[str, Any]:
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)
    return data


def recursively_get_json_files(directory: str | Path) -> List[Path]:
    return list(Path(directory).rglob("*.json"))


def get_functions_from_template(template: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    functions: List[Dict[str, Any]] = []
    for node in template:
        node_type = node.get("nodeType")
        if node_type in ("FunctionDefinition", "FunctionDeclaration"):
            functions.append(dict(node))

        children = node.get("children")
        if isinstance(children, list) and children:
            functions.extend(get_functions_from_template(children))

    return functions
