"""Gradient inversion by an honest-but-curious coordinator.

The attacker sees a model update ``delta = w_after - w_before`` and the model
``w_before``. For one local SGD step (the first momentum step equals plain SGD)
``delta = -lr * grad``, so ``-delta`` points along the training gradient of the
client's batch. The attack follows Geiping et al. (2020), "Inverting Gradients":
dummy images are optimised so that their gradient has maximal cosine similarity
with the observed one, with a total-variation prior. Labels can be read from the
sign of the last-layer bias update (Zhao et al. 2020, iDLG).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn


@dataclass(frozen=True)
class InversionSettings:
    iterations: int = 2000
    learning_rate: float = 0.1
    tv_weight: float = 1e-2
    restarts: int = 2

    def __post_init__(self) -> None:
        if self.iterations <= 0 or self.restarts <= 0:
            raise ValueError("iterations and restarts must be positive")
        if self.learning_rate <= 0 or self.tv_weight < 0:
            raise ValueError("learning_rate must be positive and tv_weight non-negative")


@dataclass
class InversionResult:
    images: torch.Tensor          # reconstructed images in normalised space
    gradient_loss: float          # 1 - cosine similarity at the end of the best restart


_DEFAULT_INVERSION_SETTINGS = InversionSettings()


def label_candidates(bias_delta: torch.Tensor) -> list[int]:
    """Classes whose output bias grew in the update.

    The cross-entropy bias gradient is ``mean(p - onehot(y))``; it is negative
    only for classes present in the batch (exactly one class for a single image).
    """
    return sorted(int(c) for c in torch.nonzero(bias_delta > 0).flatten().tolist())


def total_variation(images: torch.Tensor) -> torch.Tensor:
    dx = (images[:, :, :, 1:] - images[:, :, :, :-1]).abs().mean()
    dy = (images[:, :, 1:, :] - images[:, :, :-1, :]).abs().mean()
    return dx + dy


def _parameters(model: nn.Module) -> list[nn.Parameter]:
    return [p for p in model.parameters() if p.requires_grad]


def target_gradient(model: nn.Module, delta: Mapping[str, torch.Tensor]) -> list[torch.Tensor]:
    """Observed update, in parameter order, turned into a descent direction."""
    names = [name for name, p in model.named_parameters() if p.requires_grad]
    missing = [name for name in names if name not in delta]
    if missing:
        raise KeyError(f"update lacks parameters: {missing}")
    return [-delta[name].detach().to(torch.float32) for name in names]


def _cosine_loss(grads: Sequence[torch.Tensor], target: Sequence[torch.Tensor]) -> torch.Tensor:
    dot = sum((g * t).sum() for g, t in zip(grads, target))
    g_norm = torch.sqrt(sum(g.pow(2).sum() for g in grads))
    t_norm = torch.sqrt(sum(t.pow(2).sum() for t in target))
    return 1 - dot / (g_norm * t_norm + 1e-12)


def invert_update(
    model: nn.Module,
    delta: Mapping[str, torch.Tensor],
    labels: torch.Tensor,
    image_shape: tuple[int, int, int],
    pixel_range: tuple[float, float],
    settings: InversionSettings = _DEFAULT_INVERSION_SETTINGS,
    seed: int = 0,
) -> InversionResult:
    """Reconstruct ``len(labels)`` images whose gradient matches ``delta``."""
    if labels.ndim != 1 or labels.numel() == 0:
        raise ValueError("labels must be a non-empty 1-D tensor")
    model.eval()
    params = _parameters(model)
    target = target_gradient(model, delta)
    low, high = pixel_range
    generator = torch.Generator().manual_seed(seed)
    best: InversionResult | None = None
    milestones = [int(settings.iterations * f) for f in (3 / 8, 5 / 8, 7 / 8)]
    for _ in range(settings.restarts):
        dummy = torch.randn((labels.numel(), *image_shape), generator=generator)
        dummy = dummy.clamp(low, high).requires_grad_(True)
        optimizer = torch.optim.Adam([dummy], lr=settings.learning_rate)
        scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones, gamma=0.1)
        for _ in range(settings.iterations):
            optimizer.zero_grad()
            loss = F.cross_entropy(model(dummy), labels)
            grads = torch.autograd.grad(loss, params, create_graph=True)
            objective = _cosine_loss(grads, target) + settings.tv_weight * total_variation(dummy)
            objective.backward()
            dummy.grad.sign_()
            optimizer.step()
            scheduler.step()
            with torch.no_grad():
                dummy.clamp_(low, high)
        loss = F.cross_entropy(model(dummy), labels)
        grads = torch.autograd.grad(loss, params)
        final = float(_cosine_loss(grads, target))
        if best is None or final < best.gradient_loss:
            best = InversionResult(dummy.detach().clone(), final)
    assert best is not None
    return best


# Image-quality metrics on images scaled to [0, 1].

def psnr(reference: torch.Tensor, estimate: torch.Tensor) -> float:
    mse = float(F.mse_loss(estimate, reference))
    return float("inf") if mse == 0 else 10.0 * torch.log10(torch.tensor(1.0 / mse)).item()


def ssim(reference: torch.Tensor, estimate: torch.Tensor, window: int = 7, sigma: float = 1.5) -> float:
    """Mean structural similarity of two single images shaped (C, H, W)."""
    if reference.shape != estimate.shape or reference.ndim != 3:
        raise ValueError("ssim expects two images with the same (C, H, W) shape")
    coords = torch.arange(window, dtype=torch.float32) - (window - 1) / 2
    kernel_1d = torch.exp(-coords.pow(2) / (2 * sigma ** 2))
    kernel_1d = kernel_1d / kernel_1d.sum()
    channels = reference.shape[0]
    kernel = (kernel_1d[:, None] * kernel_1d[None, :]).expand(channels, 1, window, window)
    x, y = reference[None].float(), estimate[None].float()

    def blur(t: torch.Tensor) -> torch.Tensor:
        return F.conv2d(t, kernel, groups=channels)

    mu_x, mu_y = blur(x), blur(y)
    var_x = blur(x * x) - mu_x.pow(2)
    var_y = blur(y * y) - mu_y.pow(2)
    cov = blur(x * y) - mu_x * mu_y
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    value = ((2 * mu_x * mu_y + c1) * (2 * cov + c2)) / (
        (mu_x.pow(2) + mu_y.pow(2) + c1) * (var_x + var_y + c2))
    return float(value.mean())


def _greedy_match(scores: list[tuple[float, int, int]]) -> list[tuple[int, int, float]]:
    """One-to-one pairing, highest score first. Returns ``(true, candidate, score)``."""
    used_true: set[int] = set()
    used_cand: set[int] = set()
    pairs = []
    for score, i, j in sorted(scores, reverse=True):
        if i in used_true or j in used_cand:
            continue
        used_true.add(i)
        used_cand.add(j)
        pairs.append((i, j, score))
    return sorted(pairs)


def match_reconstructions(truth: torch.Tensor, recon: torch.Tensor) -> list[tuple[int, int, float, float]]:
    """Pair each true image with a distinct reconstruction, best SSIM first.

    Returns ``(true_index, recon_index, ssim, psnr)`` per true image. Greedy
    matching gives the attacker the benefit of the doubt: it does not need to
    know which reconstruction belongs to which image.
    """
    if recon.shape[0] < truth.shape[0]:
        raise ValueError("need at least as many reconstructions as true images")
    scores = [(ssim(truth[i], recon[j]), i, j)
              for i in range(truth.shape[0]) for j in range(recon.shape[0])]
    return [(i, j, s, psnr(truth[i], recon[j])) for i, j, s in _greedy_match(scores)]


# Analytic attack on a fully connected layer (Phong et al. 2017).

def fc_input_candidates(weight_delta: torch.Tensor, bias_delta: torch.Tensor,
                        min_bias: float = 1e-9) -> torch.Tensor:
    """Inputs of a linear layer read off its update, one candidate per output unit.

    For ``y = W x + b`` the gradients are ``dW_j = g_j x`` and ``db_j = g_j``, so
    ``dW_j / db_j = x`` exactly for a single sample. For several samples each
    row is a mixture of the inputs that reached unit ``j``; a row reached by
    only one sample still returns that sample exactly.
    """
    if weight_delta.ndim != 2 or bias_delta.shape != weight_delta.shape[:1]:
        raise ValueError("expected a (out, in) weight update and an (out,) bias update")
    keep = bias_delta.abs() > min_bias
    if not bool(keep.any()):
        return weight_delta.new_zeros((0, weight_delta.shape[1]))
    return weight_delta[keep] / bias_delta[keep, None]


def best_cosine(truth: torch.Tensor, candidates: torch.Tensor) -> list[float]:
    """For each true vector, the highest cosine similarity of any candidate.

    Candidates may be reused: the layer yields at most one candidate per output
    unit, which can be fewer than the samples behind an aggregate.
    """
    if candidates.shape[0] == 0:
        return [0.0] * truth.shape[0]
    sims = F.cosine_similarity(truth[:, None, :], candidates[None, :, :], dim=-1)
    return [float(v) for v in sims.max(dim=1).values]
