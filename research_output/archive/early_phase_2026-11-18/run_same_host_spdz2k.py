#!/usr/bin/env python3
import os
from pathlib import Path
import torch
from torch import nn
from torch.utils.data import TensorDataset
import yaml

from fl_security.federated import flower_simulation
from fl_security.smpc import local_demo


class TinyCifarModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.classifier = nn.Linear(3, 2)

    def forward(self, images):
        return self.classifier(self.pool(images).flatten(1))


def tiny_cifar_data():
    generator = torch.Generator().manual_seed(123)
    images = torch.randn(8, 3, 32, 32, generator=generator)
    labels = torch.tensor([0, 1, 0, 1, 0, 1, 0, 1], dtype=torch.long)
    train = TensorDataset(images, labels)
    test = TensorDataset(images[:4], labels[:4])
    partitions = [
        TensorDataset(images[offset:offset + 2], labels[offset:offset + 2])
        for offset in (0, 2, 4)
    ]
    flower_simulation.CIFAR10CNN = TinyCifarModel
    flower_simulation.load_cifar10_data = lambda: (train, test)
    flower_simulation.partition_data = lambda *args, **kwargs: partitions


def main():
    torch.set_num_threads(1)
    tiny_cifar_data()
    config = {
        "experiment": {"name": "same_host_spdz2k_tiny_smoke", "seed": 123, "rounds": 1},
        "federated_learning": {
            "framework": "flower", "dataset": "cifar10", "num_clients": 3,
            "fraction_train": 1.0, "local_epochs": 1, "batch_size": 2,
            "learning_rate": 0.001, "partitioning": "iid",
        },
        "mtd": {"enabled": False, "selection_strategy": "random", "change_every_round": True},
        "smpc": {
            "enabled": True, "backend": "mp_spdz_spdz2k", "fixed_point_scale": 100000,
            "num_aggregation_parties": 3, "min_clients_per_round": 2,
        },
        "attacks": {"enabled": False, "attack_type": "sign_flip", "compromised_fraction": 0.0, "strength": 1.0},
        "evaluation": {
            "output_dir": "research_output/same_host_spdz2k_tiny",
            "save_csv": True, "save_plots": False,
        },
        "flower": {"client_cpus": 1, "client_gpus": 0},
    }
    os.environ["FL_MPSPDZ_HOME"] = "/home/ubuntu/gemini/MP-SPDZ-v0.4.3"
    os.environ.pop("FL_MTD_SECRET", None)
    local_demo.run_with_local_mp_spdz(config)
    output = Path(config["evaluation"]["output_dir"]) / "same_host_spdz2k_tiny_smoke_results.csv"
    if not output.is_file():
        raise RuntimeError(f"Flower did not write expected output: {output}")
    print(f"SAME_HOST_SPDZ2K_TINY_SMOKE_PASSED {output} {output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
