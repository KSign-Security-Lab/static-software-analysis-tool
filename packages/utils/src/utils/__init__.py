import os
from typing import Callable, List, Any, Dict
import json
from multiprocessing import Pool


def multiprocess(func: Callable, args: List[Any], num_processes: int) -> List[Any]:
    with Pool(num_processes) as p:
        return p.map(func, args)


def read_json(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r") as f:
        return json.load(f)


def recursvely_get_json_files(directory: str) -> List[str]:
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith(".json"):
                files.append(os.path.join(root, filename))
    return files


def recursivelyGetFunctionsFromTemplate(
    template: Dict[str, Any],
) -> List[Dict[str, Any]]:
    functions: List[Dict[str, Any]] = []
    for node in template:
        if node["nodeType"] == "FunctionDefinition":
            functions.append(node)
        elif node["nodeType"] == "FunctionDeclaration":
            functions.append(node)
        if node["children"]:
            functions.extend(recursivelyGetFunctionsFromTemplate(node["children"]))
    return functions
