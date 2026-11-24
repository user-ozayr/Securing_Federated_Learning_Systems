import torch
import torch.nn as nn
import torch.nn.functional as F

SUPPORTED_MODELS = ("cifar10_cnn", "compact_cnn")


class CIFAR10CNN(nn.Module):
    def __init__(self):
        super(CIFAR10CNN, self).__init__()
        self.conv1 = nn.Conv2d(3, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.fc1 = nn.Linear(64 * 8 * 8, 512)
        self.fc2 = nn.Linear(512, 10)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(-1, 64 * 8 * 8)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x


class CompactCNN(nn.Module):
    """Small LeNet-style CNN sized so that every round fits SPDZ2k on one host.

    For 28x28 single-channel inputs it has 2,202 parameters:
    conv(1->4, 5x5) = 104, conv(4->8, 5x5) = 808, linear(128->10) = 1,290.
    """

    def __init__(self, in_channels: int = 1, image_size: int = 28, num_classes: int = 10,
                 width: int = 4):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, width, 5)
        self.conv2 = nn.Conv2d(width, 2 * width, 5)
        self.pool = nn.MaxPool2d(2, 2)
        spatial = ((image_size - 4) // 2 - 4) // 2
        if spatial <= 0:
            raise ValueError("image_size is too small for CompactCNN")
        self.flat = 2 * width * spatial * spatial
        self.fc = nn.Linear(self.flat, num_classes)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        return self.fc(x.reshape(x.shape[0], self.flat))


def build_model(name: str = "cifar10_cnn", dataset: str = "cifar10") -> nn.Module:
    from fl_security.federated.dataset import DATASET_SHAPES, NUM_CLASSES

    if name not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported model {name!r}; choose one of {SUPPORTED_MODELS}")
    channels, height, _ = DATASET_SHAPES[dataset]
    if name == "cifar10_cnn":
        if dataset != "cifar10":
            raise ValueError("cifar10_cnn requires the cifar10 dataset")
        return CIFAR10CNN()
    return CompactCNN(in_channels=channels, image_size=height, num_classes=NUM_CLASSES[dataset])


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.state_dict().values() if torch.is_floating_point(p))
