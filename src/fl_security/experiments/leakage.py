"""E6: what a curious coordinator can reconstruct from what it receives.

Under plaintext FedAvg the coordinator receives each selected client's model.
Under sum-only SPDZ2k it receives only the sample-weighted average of the K
models, decoded exactly as the output client decodes the protocol output.
The same attacker is run against both views, after one local SGD step (FedSGD,
the setting most favourable to the attacker). Three attacks are used:

* ``optimisation`` - gradient inversion (Geiping et al. 2020) on the deployed
  CompactCNN; quality measured by SSIM/PSNR of the best-matching image;
* ``fc_features`` - analytic read-out of the 128-d input of the CompactCNN's
  output layer; quality measured by cosine similarity to the true features;
* ``fc_input`` - analytic read-out of the input image through the first,
  fully connected layer of a probe MLP (Phong et al. 2017); SSIM/PSNR.
"""
from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader

from fl_security.attacks.gradient_inversion import (
    InversionSettings,
    best_cosine,
    fc_input_candidates,
    invert_update,
    label_candidates,
    match_reconstructions,
)
from fl_security.evaluation.statistics import summarize_values
from fl_security.federated.dataset import DATASET_SHAPES, load_dataset, partition_data
from fl_security.federated.model import CompactCNN
from fl_security.federated.training import evaluate_model, train_local
from fl_security.smpc.fixed_point import FixedPointEncoder
from fl_security.smpc.mp_spdz import _encode_weighted_model

# Match the normalisation used by load_dataset.
NORMALISATION = {"fashion_mnist": (0.2860, 0.3530), "mnist": (0.1307, 0.3081)}
METRICS = ("ssim", "psnr", "feature_cosine", "recognisable", "label_precision", "label_recall",
           "gradient_loss")


class ProbeMLP(nn.Module):
    """Probe model with a fully connected first layer (784-100-10, 79,510 parameters).

    Used only to measure the worst case of input leakage; it is not one of the
    models trained in the federated experiments.
    """

    def __init__(self, in_features: int = 784, hidden: int = 100, num_classes: int = 10):
        super().__init__()
        self.fc1 = nn.Linear(in_features, hidden)
        self.fc2 = nn.Linear(hidden, num_classes)

    def forward(self, x):
        return self.fc2(F.relu(self.fc1(x.flatten(1))))


@dataclass
class LeakageConfig:
    dataset: str = "fashion_mnist"
    num_clients: int = 12
    cohort_size: int = 4
    batch_sizes: Sequence[int] = (1, 2, 4, 8)
    model_states: Sequence[str] = ("initial", "trained")
    trials: int = 6
    client_lr: float = 0.05
    fixed_point_scale: int = 1_000_000
    seed: int = 101
    recognisable_ssim: float = 0.5
    inversion: InversionSettings = field(default_factory=InversionSettings)

    def __post_init__(self) -> None:
        if self.dataset not in NORMALISATION:
            raise ValueError(f"unsupported dataset {self.dataset!r}")
        if not 1 <= self.cohort_size < self.num_clients:
            raise ValueError("cohort_size must be in [1, num_clients - 1]")
        if self.trials <= 0 or not self.batch_sizes:
            raise ValueError("need at least one trial and one batch size")
        if set(self.model_states) - {"initial", "trained"}:
            raise ValueError("model_states must be 'initial' and/or 'trained'")


def secure_sum_aggregate(states: Sequence[Mapping[str, torch.Tensor]], counts: Sequence[int],
                         scale: int) -> dict[str, torch.Tensor]:
    """The model the SPDZ2k weighted-sum round reveals to the output client.

    Each client encodes ``n_i * w_i`` with the protocol's encoder; the parties
    add the integers; the output client divides by the scale and by ``sum n_i``.
    """
    encoder = FixedPointEncoder(scale)
    total: list[int] | None = None
    layout = None
    for state, count in zip(states, counts, strict=True):
        values, layout = _encode_weighted_model(state, count, encoder, max_clients=len(states))
        total = values if total is None else [a + b for a, b in zip(total, values)]
    assert total is not None and layout is not None
    total_examples = total[-1]
    if total_examples != sum(counts):
        raise RuntimeError("aggregated sample count does not match")
    result: dict[str, torch.Tensor] = {}
    offset = 0
    for key, shape in layout:
        size = int(np.prod(shape)) if shape else 1
        weighted = torch.tensor(total[offset:offset + size], dtype=torch.float64).reshape(shape)
        result[key] = (weighted / encoder.scale / total_examples).to(torch.float32)
        offset += size
    return result


def compact_features(model: CompactCNN, images: torch.Tensor) -> torch.Tensor:
    """Input of the CompactCNN output layer (the vector ``fc`` multiplies)."""
    with torch.no_grad():
        x = model.pool(F.relu(model.conv1(images)))
        x = model.pool(F.relu(model.conv2(x)))
        return x.reshape(x.shape[0], model.flat)


def to_unit_range(images: torch.Tensor, dataset: str) -> torch.Tensor:
    mean, std = NORMALISATION[dataset]
    return (images * std + mean).clamp(0, 1)


def pixel_range(dataset: str) -> tuple[float, float]:
    mean, std = NORMALISATION[dataset]
    return (0 - mean) / std, (1 - mean) / std


def _delta(after: Mapping[str, torch.Tensor], before: Mapping[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    return {k: after[k].float() - before[k].float() for k in before if torch.is_floating_point(before[k])}


def _label_scores(candidates: list[int], labels: Sequence[int]) -> tuple[float, float]:
    truth = {int(x) for x in labels}
    hits = len(truth & set(candidates))
    precision = hits / len(candidates) if candidates else 0.0
    return precision, hits / len(truth)


def _trial_seed(cfg: LeakageConfig, state: str, batch: int, trial: int) -> int:
    return cfg.seed * 1_000_000 + (0 if state == "initial" else 500_000) + batch * 1_000 + trial


def prepare_models(cfg: LeakageConfig, data_root: str | None):
    """Load data, partition it, and build the attacked global models.

    The last partition is reserved: the ``trained`` models are trained on it for
    one epoch, so attacked batches never overlap the data a model has seen.
    Returns ``(partitions, {state: {"cnn": model, "mlp": model}}, accuracies)``.
    """
    trainset, testset = load_dataset(cfg.dataset, data_root)
    partitions = partition_data(trainset, cfg.num_clients, "iid", seed=cfg.seed)
    channels, height, width = DATASET_SHAPES[cfg.dataset]
    torch.manual_seed(cfg.seed)
    initial = {"cnn": CompactCNN(in_channels=channels, image_size=height),
               "mlp": ProbeMLP(in_features=channels * height * width)}
    test_loader = DataLoader(testset, batch_size=1000)
    models: dict[str, dict[str, nn.Module]] = {}
    info: dict[str, float] = {}
    for state in cfg.model_states:
        models[state] = {}
        for name, base in initial.items():
            model = copy.deepcopy(base)
            if state == "trained":
                generator = torch.Generator().manual_seed(cfg.seed)
                loader = DataLoader(partitions[-1], batch_size=32, shuffle=True,
                                    generator=generator)
                model.load_state_dict(train_local(model, loader, epochs=1, lr=cfg.client_lr))
            models[state][name] = model
            info[f"{state}_{name}_test_accuracy"] = evaluate_model(copy.deepcopy(model),
                                                                   test_loader)[1]
    return partitions[:-1], models, info


def _client_round(model: nn.Module, batches: Mapping[int, tuple[torch.Tensor, torch.Tensor]],
                  cohort: Sequence[int], target: int, lr: float, scale: int, seed: int):
    """One local step per client; the two views a coordinator can have of it."""
    before = {k: v.detach().clone() for k, v in model.state_dict().items()}
    states = {}
    for client in cohort:
        torch.manual_seed(seed + client)
        states[client] = train_local(copy.deepcopy(model), [batches[client]], epochs=1, lr=lr)
    aggregate = secure_sum_aggregate([states[c] for c in cohort],
                                     [batches[c][1].numel() for c in cohort], scale)
    return {"individual": _delta(states[target], before),
            "secure_aggregate": _delta(aggregate, before)}


def run_trial(cfg: LeakageConfig, models: Mapping[str, nn.Module], partitions, state: str,
              batch: int, trial: int, attacks: Sequence[str] = ("optimisation", "fc_features",
                                                                "fc_input")):
    seed = _trial_seed(cfg, state, batch, trial)
    rng = np.random.default_rng(seed)
    cohort = sorted(int(c) for c in rng.choice(len(partitions), cfg.cohort_size, replace=False))
    target = int(rng.choice(cohort))
    batches = {}
    for client in cohort:
        subset = partitions[client]
        picks = rng.choice(len(subset), batch, replace=False)
        images = torch.stack([subset[int(i)][0] for i in picks])
        labels = torch.tensor([int(subset[int(i)][1]) for i in picks])
        batches[client] = (images, labels)
    target_images, target_labels = batches[target]
    all_labels = torch.cat([batches[c][1] for c in cohort])
    truth = to_unit_range(target_images, cfg.dataset)
    base = {"model_state": state, "batch_size": batch, "trial": trial, "seed": seed,
            "cohort": " ".join(map(str, cohort)), "target_client": target}
    rows: list[dict] = []
    examples: dict[str, np.ndarray] = {"truth": truth.numpy()}

    cnn, mlp = models["cnn"], models["mlp"]
    cnn_views = _client_round(cnn, batches, cohort, target, cfg.client_lr,
                              cfg.fixed_point_scale, seed)
    for view, delta in cnn_views.items():
        precision, recall = _label_scores(label_candidates(delta["fc.bias"]), target_labels.tolist())
        labels_seen = target_labels if view == "individual" else all_labels
        common = {**base, "view": view, "images_in_view": int(labels_seen.numel()),
                  "label_precision": precision, "label_recall": recall}
        if "fc_features" in attacks:
            candidates = fc_input_candidates(delta["fc.weight"], delta["fc.bias"])
            for i, cos in enumerate(best_cosine(compact_features(cnn, target_images), candidates)):
                rows.append({**common, "attack": "fc_features", "image_index": i,
                             "feature_cosine": cos})
        if "optimisation" in attacks:
            result = invert_update(cnn, delta, labels_seen, tuple(target_images.shape[1:]),
                                   pixel_range(cfg.dataset), cfg.inversion, seed=seed)
            recon = to_unit_range(result.images, cfg.dataset)
            pairs = match_reconstructions(truth, recon)
            examples[f"optimisation__{view}"] = recon[[j for _, j, _, _ in pairs]].numpy()
            for i, _, ssim_value, psnr_value in pairs:
                rows.append({**common, "attack": "optimisation", "image_index": i,
                             "ssim": ssim_value, "psnr": psnr_value,
                             "gradient_loss": result.gradient_loss})

    if "fc_input" in attacks:
        mlp_views = _client_round(mlp, batches, cohort, target, cfg.client_lr,
                                  cfg.fixed_point_scale, seed)
        for view, delta in mlp_views.items():
            candidates = fc_input_candidates(delta["fc1.weight"], delta["fc1.bias"])
            recon = to_unit_range(candidates.reshape(-1, *target_images.shape[1:]), cfg.dataset)
            pairs = match_reconstructions(truth, recon) if len(recon) >= len(truth) else []
            if pairs:
                examples[f"fc_input__{view}"] = recon[[j for _, j, _, _ in pairs]].numpy()
            for i, _, ssim_value, psnr_value in pairs:
                rows.append({**base, "view": view, "attack": "fc_input", "image_index": i,
                             "images_in_view": batch * (1 if view == "individual" else len(cohort)),
                             "ssim": ssim_value, "psnr": psnr_value})
    return rows, examples


def iterate_trials(cfg: LeakageConfig) -> Iterator[tuple[str, int, int]]:
    for state in cfg.model_states:
        for batch in cfg.batch_sizes:
            for trial in range(cfg.trials):
                yield state, batch, trial


def summarise(raw: pd.DataFrame, recognisable_ssim: float) -> pd.DataFrame:
    """Per (attack, model state, batch size, view): trial-level means with 95 % t-intervals."""
    raw = raw.copy()
    for column in METRICS:
        if column not in raw:
            raw[column] = np.nan
    raw["recognisable"] = np.where(raw["ssim"].notna(),
                                   (raw["ssim"] >= recognisable_ssim).astype(float), np.nan)
    keys = ["attack", "model_state", "batch_size", "view"]
    per_trial = raw.groupby(keys + ["trial"], as_index=False)[list(METRICS)].mean()
    rows = []
    for key, group in per_trial.groupby(keys):
        for metric in METRICS:
            values = group[metric].dropna()
            if values.empty:
                continue
            rows.append({**dict(zip(keys, key)), "metric": metric, **summarize_values(values)})
    return pd.DataFrame(rows)


def config_record(cfg: LeakageConfig) -> dict:
    record = asdict(cfg)
    record["batch_sizes"] = list(cfg.batch_sizes)
    record["model_states"] = list(cfg.model_states)
    return record
