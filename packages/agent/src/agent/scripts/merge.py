import json
import os

try:
    # Works when running as a module from repo root:
    #   python -m packages.agent.scripts.merge
    from packages.agent.utils.path import import_from_file, path_resolver
except ModuleNotFoundError:
    # Fallback for running the file directly:
    #   python packages/agent/scripts/merge.py
    import os
    import sys

    current_dir = os.path.dirname(__file__)  # .../packages/agent/scripts
    agent_dir = os.path.dirname(current_dir)  # .../packages/agent
    packages_dir = os.path.dirname(agent_dir)  # .../packages
    repo_root = os.path.dirname(packages_dir)  # repo root
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from packages.agent.utils.path import import_from_file, path_resolver


def main():
    _dfg_mod = import_from_file(
        "core_DFGExtractor",
        path_resolver.from_core_package("dfg/python/legacy.py"),
    )
    DFGExtractorV1_12 = getattr(_dfg_mod, "DFGExtractorV1_12")

    ast_dir = path_resolver.from_repo_root("data/test/121_AST")
    template_dir = path_resolver.from_repo_root("data/test/121_Conv")
    save_dir = path_resolver.from_repo_root("data/test/121_full")
    os.makedirs(save_dir, exist_ok=True)
    ast_files = []
    template_files = []
    for root, _, files in os.walk(ast_dir):
        for file in files:
            if file.endswith(".json"):
                ast_files.append(os.path.join(root, file))
    for root, _, files in os.walk(template_dir):
        for file in files:
            if file.endswith(".json"):
                template_files.append(os.path.join(root, file))
    ast_files.sort()
    template_files.sort()
    if len(ast_files) != len(template_files):
        raise ValueError(
            f"ast_files and template_files must have the same length: {len(ast_files)} != {len(template_files)}"
        )
    for ast_file, template_file in zip(ast_files, template_files):
        with open(template_file, "r") as f:
            template_json = json.load(f)
        with open(ast_file, "r") as f:
            ast_result = json.load(f)

        extractor = DFGExtractorV1_12(template_json, ast_result["ast_result"])

        dfg_result = extractor.run()

        with open(
            os.path.join(
                save_dir,
                f"{os.path.basename(ast_file).replace('.json', '_full.json').replace('~', '')}",  # remove ~ from file name
            ),
            "w",
        ) as f:
            json.dump(
                {
                    "file": os.path.basename(ast_file),
                    "label": (
                        0 if os.path.basename(ast_file).lower().find("bad") == -1 else 1
                    ),
                    "ast_result": ast_result["ast_result"],
                    "dfg_result": dfg_result,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )


if __name__ == "__main__":
    main()
