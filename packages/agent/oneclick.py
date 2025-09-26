# run_experiments.py
import multiprocessing as mp
import os

from train import TrainConfig, train

train_configs = [
    TrainConfig(
        epochs=30,
        save_name="default-ep30-shuffle-121-122",
        device="cuda:0",
        data_path=["../../data/test/121_full", "../../data/test/122_full"],
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
