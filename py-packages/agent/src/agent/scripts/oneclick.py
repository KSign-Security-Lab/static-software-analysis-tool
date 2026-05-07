# run_experiments.py
import multiprocessing as mp
import os
import sys

# Robust import setup for both `python -m` and direct execution
try:
    from packages.agent.utils.path import path_resolver
except ModuleNotFoundError:
    current_dir = os.path.dirname(__file__)  # .../packages/agent/scripts
    agent_dir = os.path.dirname(current_dir)  # .../packages/agent
    packages_dir = os.path.dirname(agent_dir)  # .../packages
    repo_root = os.path.dirname(packages_dir)  # repo root
    # Ensure both repo root and agent package dir are available for imports like `dataset.*`
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    from packages.agent.utils.path import path_resolver

# Robust import of TrainConfig and train
try:
    # Prefer absolute import via namespace
    from packages.agent import TrainConfig, train
except ModuleNotFoundError:
    # Ensure agent_dir is on sys.path then retry alternatives
    try:
        current_dir = os.path.dirname(__file__)
        agent_dir = os.path.dirname(current_dir)
        if agent_dir not in sys.path:
            sys.path.insert(0, agent_dir)
        from agent import TrainConfig, train  # type: ignore
    except Exception:
        # Last resort: relative import when executed as module
        from .. import TrainConfig, train  # type: ignore

train_configs = [
    TrainConfig(
        save_name="default-ep10-shuffle-121",
        device="cuda:0",
        data_path=[
            path_resolver.from_repo_root("data/test/121_full"),
        ],
        epochs=10,
        shuffle=True,
    ),
    # TrainConfig(epochs=300, mode="ast", save_name="ast_only"),
    # TrainConfig(epochs=300, mode="dfg", save_name="dfg_only"),
    # TrainConfig(epochs=300, lr=0.001, save_name="focal_loss"),
    # TrainConfig(
    #     epochs=300,
    #     gnn_layers=10,
    #     fusion_depth=10,
    #     hid=128,
    #     shuffle_buffer=10000,
    #     num_workers=0,
    #     pin_memory=False,
    #     seed=42,
    #     loss="focal",
    #     save_name="deep_model",
    # ),
    # TrainConfig(epochs=300, model="late_fusion", save_name="late_fusion"),
]

if __name__ == "__main__":
    for cfg in train_configs:
        train(cfg)
