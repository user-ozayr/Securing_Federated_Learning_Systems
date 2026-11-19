"""Compact model, model factory and partitioning strategies."""
import numpy as np
import pytest
import torch
from torch.utils.data import TensorDataset

from fl_security.federated.dataset import partition_data
from fl_security.federated.model import CIFAR10CNN, CompactCNN, build_model, count_parameters


class _Labelled(TensorDataset):
    def __init__(self, labels):
        super().__init__(torch.zeros(len(labels), 1), torch.tensor(labels))
        self.targets = list(labels)


def test_compact_cnn_size_and_forward_shape():
    model = build_model("compact_cnn", "fashion_mnist")
    assert isinstance(model, CompactCNN)
    assert count_parameters(model) == 2202
    assert model(torch.zeros(5, 1, 28, 28)).shape == (5, 10)
    cifar = build_model("compact_cnn", "cifar10")
    assert cifar(torch.zeros(2, 3, 32, 32)).shape == (2, 10)
    assert isinstance(build_model("cifar10_cnn", "cifar10"), CIFAR10CNN)


def test_model_factory_rejects_invalid_combinations():
    with pytest.raises(ValueError):
        build_model("cifar10_cnn", "mnist")
    with pytest.raises(ValueError):
        build_model("resnet", "mnist")


def test_iid_partition_is_unchanged_and_covers_dataset():
    data = _Labelled([i % 10 for i in range(100)])
    parts = partition_data(data, 4, "iid", seed=3)
    expected = np.array_split(np.random.default_rng(3).permutation(100), 4)
    assert [list(p.indices) for p in parts] == [chunk.tolist() for chunk in expected]


def test_dirichlet_partition_is_disjoint_complete_and_skewed():
    labels = [i % 10 for i in range(2000)]
    parts = partition_data(_Labelled(labels), 5, "dirichlet", seed=4, alpha=0.3, min_samples=20)
    indices = [i for p in parts for i in p.indices]
    assert sorted(indices) == list(range(2000))
    assert min(len(p) for p in parts) >= 20
    histograms = [np.bincount([labels[i] for i in p.indices], minlength=10) for p in parts]
    assert max(h.max() / h.sum() for h in histograms) > 0.2
    with pytest.raises(ValueError):
        partition_data(_Labelled(labels), 5, "dirichlet", seed=4, alpha=0.0)
