"""Gradient inversion attack and the E6 leakage study helpers."""
import pandas as pd
import pytest
import torch

from fl_security.attacks.gradient_inversion import (
    InversionSettings,
    best_cosine,
    fc_input_candidates,
    invert_update,
    label_candidates,
    match_reconstructions,
    psnr,
    ssim,
    total_variation,
)
from fl_security.experiments.leakage import (
    ProbeMLP,
    compact_features,
    secure_sum_aggregate,
    summarise,
)
from fl_security.federated.model import CompactCNN
from fl_security.federated.training import train_local


def _one_step(model, images, labels, lr=0.05):
    before = {k: v.clone() for k, v in model.state_dict().items()}
    local = CompactCNN()
    local.load_state_dict(before)
    after = train_local(local, [(images, labels)], epochs=1, lr=lr)
    return {k: after[k] - before[k] for k in before}


def test_single_image_label_is_read_from_bias_update():
    torch.manual_seed(0)
    model = CompactCNN()
    for label in (0, 3, 9):
        delta = _one_step(model, torch.randn(1, 1, 28, 28), torch.tensor([label]))
        assert label_candidates(delta["fc.bias"]) == [label]


def test_update_equals_negative_scaled_gradient():
    torch.manual_seed(1)
    model = CompactCNN()
    images, labels = torch.randn(2, 1, 28, 28), torch.tensor([1, 4])
    delta = _one_step(model, images, labels, lr=0.1)
    loss = torch.nn.functional.cross_entropy(model(images), labels)
    grads = torch.autograd.grad(loss, list(model.parameters()))
    for (name, _), grad in zip(model.named_parameters(), grads):
        assert torch.allclose(delta[name], -0.1 * grad, atol=1e-6)


def test_ssim_and_psnr_behave():
    image = torch.rand(1, 28, 28)
    assert ssim(image, image) == pytest.approx(1.0, abs=1e-5)
    assert psnr(image, image) == float("inf")
    noisy = (image + 0.3 * torch.randn_like(image)).clamp(0, 1)
    assert ssim(image, noisy) < 0.9
    assert psnr(image, noisy) < 20
    with pytest.raises(ValueError):
        ssim(image, torch.rand(1, 27, 28))


def test_matching_is_one_to_one():
    truth = torch.rand(2, 1, 28, 28)
    recon = torch.stack([torch.rand(1, 28, 28), truth[1], truth[0]])
    pairs = match_reconstructions(truth, recon)
    assert [(i, j) for i, j, _, _ in pairs] == [(0, 2), (1, 1)]
    with pytest.raises(ValueError):
        match_reconstructions(truth, recon[:1])


def test_total_variation_is_zero_for_constant_images():
    assert float(total_variation(torch.ones(2, 1, 8, 8))) == 0.0


def test_inversion_reduces_gradient_mismatch():
    torch.manual_seed(2)
    model = CompactCNN()
    image, label = torch.rand(1, 1, 28, 28), torch.tensor([5])
    delta = _one_step(model, image, label)
    short = invert_update(model, delta, label, (1, 28, 28), (0.0, 1.0),
                          InversionSettings(iterations=1, restarts=1))
    longer = invert_update(model, delta, label, (1, 28, 28), (0.0, 1.0),
                           InversionSettings(iterations=150, restarts=1))
    assert longer.images.shape == (1, 1, 28, 28)
    assert longer.gradient_loss < short.gradient_loss
    assert float(longer.images.min()) >= 0.0 and float(longer.images.max()) <= 1.0


def test_inversion_rejects_bad_input():
    model = CompactCNN()
    delta = {k: torch.zeros_like(v) for k, v in model.state_dict().items()}
    with pytest.raises(ValueError):
        invert_update(model, delta, torch.tensor([]), (1, 28, 28), (0.0, 1.0))
    with pytest.raises(KeyError):
        invert_update(model, {}, torch.tensor([1]), (1, 28, 28), (0.0, 1.0))
    with pytest.raises(ValueError):
        InversionSettings(iterations=0)


def test_secure_sum_aggregate_matches_weighted_mean():
    torch.manual_seed(3)
    states = [{k: v.clone() for k, v in CompactCNN().state_dict().items()} for _ in range(4)]
    counts = [1, 2, 3, 4]
    result = secure_sum_aggregate(states, counts, scale=1_000_000)
    for key in states[0]:
        expected = sum(s[key].double() * n for s, n in zip(states, counts)) / sum(counts)
        assert torch.allclose(result[key].double(), expected, atol=1e-6)


def test_summary_counts_trials_not_images():
    raw = pd.DataFrame([
        {"attack": "optimisation", "model_state": "initial", "batch_size": 2, "view": v,
         "trial": t, "image_index": i, "ssim": s, "psnr": 10.0, "gradient_loss": 0.1,
         "label_precision": 1.0, "label_recall": 1.0}
        for v, s in (("individual", 0.8), ("secure_aggregate", 0.1))
        for t in range(3) for i in range(2)
    ] + [
        {"attack": "fc_features", "model_state": "initial", "batch_size": 2, "view": "individual",
         "trial": t, "image_index": 0, "feature_cosine": 0.9} for t in range(3)
    ])
    summary = summarise(raw, recognisable_ssim=0.5)
    rec = summary[(summary.metric == "recognisable")].set_index("view")
    assert rec.loc["individual", "mean"] == 1.0
    assert rec.loc["secure_aggregate", "mean"] == 0.0
    assert set(summary["n"]) == {3}
    features = summary[summary.attack == "fc_features"]
    assert set(features.metric) == {"feature_cosine"}


def test_fc_layer_returns_single_input_exactly():
    torch.manual_seed(4)
    layer = torch.nn.Linear(6, 3)
    x = torch.randn(1, 6)
    loss = torch.nn.functional.cross_entropy(layer(x), torch.tensor([2]))
    grad_w, grad_b = torch.autograd.grad(loss, [layer.weight, layer.bias])
    candidates = fc_input_candidates(-0.05 * grad_w, -0.05 * grad_b)
    assert candidates.shape == (3, 6)
    assert torch.allclose(candidates, x.expand(3, 6), atol=1e-5)
    assert best_cosine(x, candidates)[0] == pytest.approx(1.0, abs=1e-6)


def test_fc_candidates_handle_inactive_units():
    assert fc_input_candidates(torch.zeros(4, 5), torch.zeros(4)).shape == (0, 5)
    assert best_cosine(torch.ones(2, 5), torch.zeros(0, 5)) == [0.0, 0.0]
    with pytest.raises(ValueError):
        fc_input_candidates(torch.zeros(4, 5), torch.zeros(5))


def test_probe_model_and_features():
    mlp = ProbeMLP()
    assert sum(p.numel() for p in mlp.parameters()) == 79_510
    cnn = CompactCNN()
    images = torch.randn(3, 1, 28, 28)
    features = compact_features(cnn, images)
    assert features.shape == (3, 128)
    assert torch.allclose(cnn.fc(features), cnn(images), atol=1e-6)
