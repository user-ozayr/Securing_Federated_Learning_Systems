"""Datasets and client partitions for the federated experiments."""
from __future__ import annotations

import os

import numpy as np
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import Subset

SUPPORTED_DATASETS = ("cifar10", "mnist", "fashion_mnist")
SUPPORTED_PARTITIONS = ("iid", "label_sorted", "dirichlet")

# Image geometry used by models and the backdoor trigger: (channels, height, width)
DATASET_SHAPES = {
    "cifar10": (3, 32, 32),
    "mnist": (1, 28, 28),
    "fashion_mnist": (1, 28, 28),
}
NUM_CLASSES = {"cifar10": 10, "mnist": 10, "fashion_mnist": 10}


def _data_root(root: str | None) -> str:
    return root or os.environ.get("FL_DATA_ROOT", "./data")


def load_cifar10_data(root: str | None = None):
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))
    ])
    data_root = _data_root(root)
    trainset = torchvision.datasets.CIFAR10(root=data_root, train=True, download=True, transform=transform)
    testset = torchvision.datasets.CIFAR10(root=data_root, train=False, download=True, transform=transform)
    return trainset, testset


def load_dataset(name: str = "cifar10", root: str | None = None):
    """Return (trainset, testset) with normalised tensors."""
    if name not in SUPPORTED_DATASETS:
        raise ValueError(f"unsupported dataset {name!r}; choose one of {SUPPORTED_DATASETS}")
    if name == "cifar10":
        return load_cifar10_data(root)
    data_root = _data_root(root)
    if name == "mnist":
        transform = transforms.Compose([
            transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))
        ])
        cls = torchvision.datasets.MNIST
    else:
        transform = transforms.Compose([
            transforms.ToTensor(), transforms.Normalize((0.2860,), (0.3530,))
        ])
        cls = torchvision.datasets.FashionMNIST
    trainset = cls(root=data_root, train=True, download=True, transform=transform)
    testset = cls(root=data_root, train=False, download=True, transform=transform)
    return trainset, testset


def dataset_targets(dataset) -> np.ndarray:
    targets = getattr(dataset, "targets", None)
    if targets is None:
        raise ValueError("dataset does not expose targets")
    return np.asarray(targets)


def partition_data(dataset, num_clients, partitioning="iid", seed=42, alpha: float = 0.5,
                   min_samples: int = 10):
    """Split ``dataset`` into ``num_clients`` subsets.

    * ``iid``: random equal-size split;
    * ``label_sorted``: two label-sorted shards per client (pathological non-IID);
    * ``dirichlet``: per-class proportions drawn from Dir(alpha) (Hsu et al. 2019),
      resampled until every client has at least ``min_samples`` examples.
    """
    if num_clients <= 0:
        raise ValueError("num_clients must be positive")
    if partitioning not in SUPPORTED_PARTITIONS:
        raise ValueError(f"unsupported partitioning strategy: {partitioning}")
    rng = np.random.default_rng(seed)
    if partitioning == "iid":
        return [Subset(dataset, chunk.tolist()) for chunk in np.array_split(rng.permutation(len(dataset)), num_clients)]
    targets = dataset_targets(dataset)
    if partitioning == "label_sorted":
        shards = np.array_split(np.argsort(targets), num_clients * 2)
        shard_order = rng.permutation(len(shards))
        return [Subset(dataset, np.concatenate([shards[i] for i in group]).tolist())
                for group in np.array_split(shard_order, num_clients)]
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("dirichlet alpha must be positive")
    classes = np.unique(targets)
    for _ in range(1000):
        assignment: list[list[int]] = [[] for _ in range(num_clients)]
        for cls in classes:
            indices = rng.permutation(np.flatnonzero(targets == cls))
            proportions = rng.dirichlet(np.full(num_clients, alpha))
            cuts = (np.cumsum(proportions)[:-1] * len(indices)).astype(int)
            for client, part in enumerate(np.split(indices, cuts)):
                assignment[client].extend(part.tolist())
        if min(len(items) for items in assignment) >= min_samples:
            return [Subset(dataset, sorted(items)) for items in assignment]
    raise RuntimeError("could not draw a Dirichlet partition with the minimum client size")
