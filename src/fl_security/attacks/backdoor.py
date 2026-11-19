"""BadNets-style trigger backdoor for image classification (Gu et al., 2017).

A malicious client stamps a small square patch onto a fraction of its training
images and relabels them with a target class. Attack success rate (ASR) is the
fraction of *test* images whose true class differs from the target that the
global model assigns to the target class once the trigger is applied. ASR is
reported separately from clean accuracy.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch

# Normalisation used by fl_security.federated.dataset (mean, std per channel).
NORMALIZATION = {
    "mnist": ((0.1307,), (0.3081,)),
    "fashion_mnist": ((0.2860,), (0.3530,)),
    "cifar10": ((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
}


@dataclass(frozen=True)
class BackdoorTrigger:
    dataset: str = "fashion_mnist"
    target_label: int = 0
    size: int = 4
    margin: int = 1

    def __post_init__(self) -> None:
        if self.dataset not in NORMALIZATION:
            raise ValueError(f"unsupported backdoor dataset {self.dataset!r}")
        if not 0 <= self.target_label <= 9:
            raise ValueError("target_label must be a class index in [0, 9]")
        if not 1 <= self.size <= 8 or not 0 <= self.margin <= 4:
            raise ValueError("trigger size must be in [1, 8] and margin in [0, 4]")

    def _patch_values(self, channels: int, device, dtype) -> torch.Tensor:
        mean, std = NORMALIZATION[self.dataset]
        if len(mean) != channels:
            raise ValueError("trigger normalisation does not match image channels")
        # A white patch: raw pixel value 1.0 after the dataset normalisation.
        return torch.tensor([(1.0 - m) / s for m, s in zip(mean, std)], device=device, dtype=dtype)

    def apply(self, images: torch.Tensor) -> torch.Tensor:
        """Return a copy of a (N, C, H, W) batch with the trigger stamped on."""
        if images.ndim != 4:
            raise ValueError("expected a batch of images with shape (N, C, H, W)")
        result = images.clone()
        _, channels, height, width = result.shape
        top = height - self.margin - self.size
        left = width - self.margin - self.size
        if top < 0 or left < 0:
            raise ValueError("trigger does not fit inside the image")
        value = self._patch_values(channels, result.device, result.dtype)
        result[:, :, top : top + self.size, left : left + self.size] = value.view(1, channels, 1, 1)
        return result

    def poison_batch(self, images: torch.Tensor, labels: torch.Tensor, fraction: float,
                     generator: torch.Generator | None = None) -> tuple[torch.Tensor, torch.Tensor]:
        """Stamp the trigger on ``fraction`` of the batch and relabel those samples."""
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("poison fraction must be in [0, 1]")
        count = int(round(fraction * images.shape[0]))
        if count == 0:
            return images, labels
        order = torch.randperm(images.shape[0], generator=generator)[:count]
        images = images.clone()
        labels = labels.clone()
        images[order] = self.apply(images[order])
        labels[order] = self.target_label
        return images, labels


@torch.no_grad()
def attack_success_rate(model: torch.nn.Module, dataloader, trigger: BackdoorTrigger,
                        device="cpu") -> float:
    """Fraction of non-target test images classified as the target once triggered."""
    model.to(device)
    model.eval()
    hits = total = 0
    for images, labels in dataloader:
        images, labels = images.to(device), labels.to(device)
        keep = labels != trigger.target_label
        if not bool(keep.any()):
            continue
        predictions = model(trigger.apply(images[keep])).argmax(dim=1)
        hits += int((predictions == trigger.target_label).sum().item())
        total += int(keep.sum().item())
    if total == 0:
        raise ValueError("no non-target samples available for attack success rate")
    return hits / total
