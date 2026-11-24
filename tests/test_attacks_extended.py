"""Backdoor, scaled replacement, adaptive scaling and malicious placement."""
import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader, TensorDataset

from fl_security.attacks.backdoor import BackdoorTrigger, attack_success_rate
from fl_security.attacks.byzantine import ByzantineAttacker


def _config(**attacks):
    base = {"enabled": True, "attack_type": "backdoor", "compromised_fraction": 0.25}
    base.update(attacks)
    return {
        "experiment": {"seed": 101},
        "federated_learning": {"dataset": "fashion_mnist", "fraction_train": 0.34},
        "attacks": base,
    }


def test_trigger_stamps_patch_and_poisons_requested_fraction():
    trigger = BackdoorTrigger(dataset="fashion_mnist", target_label=0, size=4)
    images = torch.zeros(10, 1, 28, 28)
    stamped = trigger.apply(images)
    value = (1.0 - 0.2860) / 0.3530
    assert torch.allclose(stamped[:, :, 23:27, 23:27], torch.full((10, 1, 4, 4), value))
    assert torch.count_nonzero(stamped[:, :, :23, :]) == 0
    labels = torch.arange(10) % 10
    generator = torch.Generator().manual_seed(1)
    poisoned_images, poisoned_labels = trigger.poison_batch(images, labels, 0.5, generator)
    changed = (poisoned_images.reshape(10, -1) != 0).any(dim=1)
    assert int(changed.sum()) == 5
    assert torch.all(poisoned_labels[changed] == 0)
    assert torch.equal(images, torch.zeros(10, 1, 28, 28))  # The original inputs must remain unchanged.


def test_attack_success_rate_counts_only_non_target_samples():
    trigger = BackdoorTrigger(dataset="fashion_mnist", target_label=3, size=2)

    class AlwaysTarget(torch.nn.Module):
        def forward(self, x):
            out = torch.zeros(x.shape[0], 10)
            out[:, 3] = 1.0
            return out

    data = TensorDataset(torch.zeros(8, 1, 28, 28), torch.tensor([3, 3, 1, 2, 4, 5, 6, 7]))
    assert attack_success_rate(AlwaysTarget(), DataLoader(data, batch_size=4), trigger) == 1.0


def test_scaled_replacement_and_backdoor_multiply_the_update():
    global_state = {"w": torch.tensor([1.0, 1.0]), "steps": torch.tensor(1)}
    local_state = {"w": torch.tensor([2.0, 0.0]), "steps": torch.tensor(2)}
    for attack in ("scaled_replacement", "backdoor"):
        attacker = ByzantineAttacker(_config(attack_type=attack, boost=4.0), 12)
        cid = next(iter(attacker.malicious_clients))
        result = attacker.perturb_update(cid, 1, global_state, local_state)
        assert torch.allclose(result["w"], torch.tensor([5.0, -3.0]))
        assert torch.equal(result["steps"], torch.tensor(2))
    assert ByzantineAttacker(_config(attack_type="scaled_replacement"), 12).data_poisoning(
        next(iter(ByzantineAttacker(_config(attack_type="scaled_replacement"), 12).malicious_clients)), 1
    ) == "label_flip"


def test_adaptive_backdoor_scales_to_the_expected_threshold():
    attacker = ByzantineAttacker(_config(attack_type="adaptive_backdoor", adaptive_norm_fraction=0.5), 12)
    cid = next(iter(attacker.malicious_clients))
    global_state = {"w": torch.zeros(2)}
    local_state = {"w": torch.tensor([3.0, 4.0])}          # This update has a norm of 5.
    result = attacker.perturb_update(cid, 1, global_state, local_state, threshold_estimate=2.0)
    assert torch.allclose(torch.linalg.vector_norm(result["w"]), torch.tensor(1.0))


def test_stratified_placement_matches_population_share_in_static_cohort():
    for seed in range(20):
        config = _config(num_malicious=3, placement="stratified")
        config["experiment"]["seed"] = seed
        attacker = ByzantineAttacker(config, 12)
        assert len(attacker.malicious_clients) == 3
        assert len(attacker.malicious_clients & {0, 1, 2, 3}) == 1


def test_random_placement_is_unchanged_from_previous_implementation():
    config = {"experiment": {"seed": 42}, "attacks": {"enabled": True, "attack_type": "sign_flip",
                                                     "compromised_fraction": 0.4}}
    attacker = ByzantineAttacker(config, 5)
    expected = set(int(x) for x in np.random.default_rng(42 + 20_000).choice(5, 2, replace=False))
    assert attacker.malicious_clients == expected


def test_round_assignment_overrides_fixed_set():
    attacker = ByzantineAttacker(_config(num_malicious=2), 12)
    attacker.set_round_assignment({1: {5, 6}, 2: {7, 8}})
    assert attacker.is_malicious(5, 1) and not attacker.is_malicious(5, 2)
    assert attacker.is_malicious(8, 2) and not attacker.is_malicious(8, 3)
    with pytest.raises(ValueError):
        attacker.set_malicious_clients({1})


def test_invalid_attack_settings_are_rejected():
    with pytest.raises(ValueError):
        ByzantineAttacker(_config(attack_type="unknown"), 12)
    with pytest.raises(ValueError):
        ByzantineAttacker(_config(boost=0.0), 12)
    with pytest.raises(ValueError):
        ByzantineAttacker(_config(placement="nowhere"), 12)
    with pytest.raises(ValueError):
        ByzantineAttacker(_config(backdoor={"poison_fraction": 1.5}), 12)
