import glob
import json
import os

from DFGExtractor import DFGExtractor


def load_json(file_path: str):
    with open(file_path, "r") as f:
        return json.load(f)


def save_json(data: dict, file_path: str):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def check_pair(template_files: list[str], ast_files: list[str]):
    if len(template_files) != len(ast_files):
        raise ValueError(
            f"template_files and ast_files must have the same length: {len(template_files)} != {len(ast_files)}, but found {len(template_files)} template files and {len(ast_files)} ast files"
        )
    sorted_template_files = sorted(template_files)
    sorted_ast_files = sorted(ast_files)
    for template_file, ast_file in zip(sorted_template_files, sorted_ast_files):
        template_basename = template_file.split("/")[-1].split(".json")[0]
        ast_basename = ast_file.split("/")[-1].split(".json")[0]
        if template_basename != ast_basename:
            raise ValueError(
                f"template_file {template_file} and ast_file {ast_file} must have the same basename, but found {template_basename} and {ast_basename}"
            )

    return True


def generate_dfg(template_file: str, ast_file: str, full_dataset_save_dir: str):
    os.makedirs(full_dataset_save_dir, exist_ok=True)
    template = load_json(template_file)
    full = {}
    ast = load_json(ast_file)
    dfg = DFGExtractor(template, ast["ast_result"]).run()
    full_file = full_dataset_save_dir + "/" + template_file.split("/")[-1]
    full["file"] = ast["file"]
    full["label"] = 1 if "bad" in template_file.lower() else 0
    full["ast_result"] = ast["ast_result"]
    full["dfg_result"] = dfg
    save_json(full, full_file)


def main(template_dir: str, ast_dir: str, full_dataset_save_dir: str):
    template_files = glob.glob(os.path.join(template_dir, "*.json"))
    ast_files = glob.glob(os.path.join(ast_dir, "*.json"))
    check_pair(template_files, ast_files)
    for template_file, ast_file in zip(template_files, ast_files):
        generate_dfg(template_file, ast_file, full_dataset_save_dir)


if __name__ == "__main__":
    CWE121 = {
        "template_dir": "../../data/test/121_Conv",
        "ast_dir": "../../data/test/121_result",
        "full_dataset_save_dir": "../../data/test/121_full",
    }
    main(
        CWE121["template_dir"],
        CWE121["ast_dir"],
        CWE121["full_dataset_save_dir"],
    )
    CWE122 = {
        "template_dir": "../../data/test/122_Conv",
        "ast_dir": "../../data/test/122_result",
        "full_dataset_save_dir": "../../data/test/122_full",
    }
    main(
        CWE122["template_dir"],
        CWE122["ast_dir"],
        CWE122["full_dataset_save_dir"],
    )
