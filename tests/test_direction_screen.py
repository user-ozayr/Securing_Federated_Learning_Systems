"""Moving-target direction screen: reference semantics, subsets and the evasive attacker."""
import pytest
import torch

from fl_security.attacks.byzantine import ByzantineAttacker, _copy_coordinates
from fl_security.experiments.grid import CONFIGS, STUDIES
from fl_security.smpc.robust import (
    RING_MODULUS,
    SecureDefenceConfig,
    _sign_bit,
    direction_key,
    direction_screen,
    result_from_outputs,
    robust_reference,
    round_arguments,
    validate_direction,
)

SECRET = b"k" * 32


def _defence(**extra):
    base = dict(mode="clip_screen", threshold="adaptive", static_norm=4.0, min_norm=0.25,
                max_norm=16.0, max_valid_norm=64.0, fractional_bits=14, clip_bits=8,
                direction_check=True)
    base.update(extra)
    return SecureDefenceConfig(**base)


def test_majority_of_the_others_and_agreement_counts():
    honest = [5, -3, 7, -1, 2, -6]
    inputs = [honest, honest, honest, [-v for v in honest]]
    passed, agreement = direction_screen(inputs, range(6), min_agree=4)
    assert agreement == [6, 6, 6, 0]
    assert passed == [1, 1, 1, 0]


def test_zero_counts_as_non_negative_and_ties_as_positive():
    # K = 3: the others are two clients; one positive and one negative is a tie -> positive
    inputs = [[0], [1], [-1]]
    _, agreement = direction_screen(inputs, [0], min_agree=1)
    # client 0 sees (+, -): tie -> majority +, own sign + (zero) -> agrees
    assert agreement[0] == 1


def test_signs_follow_the_64_bit_ring():
    negative_in_ring = RING_MODULUS - 5      # represents -5
    inputs = [[negative_in_ring], [-3], [-2], [4]]
    _, agreement = direction_screen(inputs, [0], min_agree=1)
    assert agreement == [1, 1, 1, 0]


def test_rejected_client_leaves_the_aggregate():
    cfg = _defence()
    honest = [100, -50, 30, -20]
    inputs = [honest, honest, honest, [-v for v in honest]]
    weights = [1, 1, 1, 1]
    spec = cfg.round_spec(weights)
    plain = robust_reference(inputs, weights, spec)
    screened = robust_reference(inputs, weights, spec, direction_indices=[0, 1, 2, 3], min_agree=3)
    assert plain.accepted == [1, 1, 1, 1]
    assert screened.accepted == [1, 1, 1, 0]
    assert screened.direction_failed == [0, 0, 0, 1]
    # equal honest norms: nobody is clipped, each accepted client enters with 2^g
    assert screened.coefficients[0] == 1 << cfg.clip_bits
    assert screened.totals == [3 * (1 << cfg.clip_bits) * v for v in honest]


def test_reference_without_screen_is_unchanged():
    cfg = _defence(direction_check=False)
    inputs = [[3, -4], [1, 2], [-2, 2]]
    weights = [1, 1, 1]
    spec = cfg.round_spec(weights)
    result = robust_reference(inputs, weights, spec)
    assert result.direction_failed == [] and result.agreement == []


def test_subset_selection_is_keyed_sized_and_round_dependent():
    cfg = _defence(direction_subset="secret", direction_fraction=0.25)
    first = cfg.direction_indices(2202, direction_key(SECRET, 1))
    again = cfg.direction_indices(2202, direction_key(SECRET, 1))
    other_round = cfg.direction_indices(2202, direction_key(SECRET, 2))
    other_key = cfg.direction_indices(2202, direction_key(b"z" * 32, 1))
    assert first == again and len(first) == 550 and first == sorted(set(first))
    assert first != other_round and first != other_key
    assert _defence(direction_subset="all").direction_indices(10, None) == list(range(10))
    with pytest.raises(ValueError):
        cfg.direction_indices(2202, None)


def test_configuration_validation():
    assert _defence(direction_min_agreement=0.5).min_agreement_count(550) == 275
    assert _defence(direction_min_agreement=0.52).min_agreement_count(550) == 286
    for bad in ({"direction_subset": "partial"}, {"direction_fraction": 0},
                {"direction_min_agreement": 1.5}, {"direction_check": 1}):
        with pytest.raises(ValueError):
            _defence(**bad)
    with pytest.raises(ValueError):
        direction_key(b"short", 1)


def _states():
    base = {"w": torch.zeros(2, 3), "b": torch.zeros(2), "steps": torch.tensor(5)}
    poisoned = {"w": torch.full((2, 3), 2.0), "b": torch.full((2,), 2.0), "steps": torch.tensor(5)}
    clean = {"w": torch.full((2, 3), -1.0), "b": torch.full((2,), -1.0), "steps": torch.tensor(5)}
    return base, poisoned, clean


def test_copy_coordinates_uses_the_flat_defence_order():
    base, poisoned, clean = _states()
    mixed = _copy_coordinates(base, poisoned, clean, [0, 5, 7])
    flat = torch.cat([mixed["w"].reshape(-1), mixed["b"]])
    assert flat.tolist() == [-1, 2, 2, 2, 2, -1, 2, -1]
    assert int(mixed["steps"]) == 5


def test_evasive_attacker_hides_in_known_coordinates():
    config = {"experiment": {"seed": 7}, "federated_learning": {"dataset": "fashion_mnist"},
              "attacks": {"enabled": True, "attack_type": "evasive_backdoor", "num_malicious": 1,
                          "boost": 1.0}}
    attacker = ByzantineAttacker(config, num_clients=4)
    victim = next(iter(attacker.malicious_clients))
    assert attacker.needs_clean_update(victim, 1)
    base, poisoned, clean = _states()
    out = attacker.perturb_update(victim, 1, base, poisoned, threshold_estimate=None,
                                  clean_state_dict=clean, known_indices=[1, 2])
    flat = torch.cat([out["w"].reshape(-1), out["b"]])
    assert flat[1] == flat[2] == -1 and flat[0] == 2
    with pytest.raises(ValueError):
        attacker.perturb_update(victim, 1, base, poisoned)
    guessed = attacker.perturb_update(victim, 1, base, poisoned, clean_state_dict=clean)
    flat = torch.cat([guessed["w"].reshape(-1), guessed["b"]])
    assert int((flat == -1).sum()) == 2          # 25 % of 8 coordinates guessed


def test_sign_test_is_the_msb_of_the_low_32_bits():
    assert [_sign_bit(v) for v in (0, 5, -5, (1 << 31) - 1, -(1 << 31))] == [0, 0, 1, 0, 1]
    # beyond 2^31 the bit is a fixed function of the value (what MP-SPDZ computes)
    assert _sign_bit(1 << 31) == 1 and _sign_bit((1 << 40) + 5) == 0
    assert _sign_bit(RING_MODULUS - 7) == 1


def test_round_arguments_with_and_without_direction():
    cfg = _defence()
    spec = cfg.round_spec([1, 1, 1])
    base = round_arguments([2, 0, 1], [5, 5, 5], [1, 1, 1], 11, 12, 14000, 256, spec)
    assert len(base) == 8
    extended = round_arguments([2, 0, 1], [5, 5, 5], [1, 1, 1], 11, 12, 14000, 256, spec,
                               direction={"min_agree": 2, "indices": [0, 4, 9]})
    assert extended[:8] == base and extended[8:] == ["2", "0,4,9"]


@pytest.mark.parametrize("bad", [
    {"min_agree": 2, "indices": []},
    {"min_agree": 2, "indices": [3, 1]},
    {"min_agree": 2, "indices": [1, 1]},
    {"min_agree": 2, "indices": [0, 10]},
    {"min_agree": 0, "indices": [0, 1]},
    {"min_agree": 3, "indices": [0, 1]},
    {"indices": [0, 1]},
    {"min_agree": 1, "indices": [0], "extra": 1},
])
def test_direction_specification_is_validated(bad):
    with pytest.raises(ValueError):
        validate_direction(bad, dimension=10)


def test_outputs_with_direction_flags():
    k, d = 3, 2
    outputs = [100, 1, 1, 1, 0, 0, 1, 0, 0, 0, 1, 7, -7]
    result = result_from_outputs(outputs, k, d, direction=True)
    assert result.accepted == [1, 1, 0] and result.clip_flags == [0, 1, 0]
    assert result.direction_failed == [0, 0, 1] and result.totals == [7, -7]
    with pytest.raises(RuntimeError):
        result_from_outputs(outputs, k, d)            # length does not fit without flags
    plain = result_from_outputs(outputs[:8] + outputs[11:], k, d)
    assert plain.direction_failed == []


def test_hidden_flags_without_reveal():
    cfg = _defence(reveal_client_flags=False)
    inputs = [[5, 3], [4, 2], [-5, -3]]
    spec = cfg.round_spec([1, 1, 1])
    result = robust_reference(inputs, [1, 1, 1], spec, direction_indices=[0, 1], min_agree=2)
    assert result.direction_failed == [0, 0, 0]       # not revealed ...
    assert result.accepted[2] == 0                    # ... but still rejected


def test_analysis_skips_unrecorded_screened_rounds():
    import numpy as np

    from fl_security.experiments.analysis import _round_rows

    config = {"defences": {"norm_defence_reference": {
        "enabled": True, "mode": "clip_screen", "threshold": "adaptive", "static_norm": 4.0,
        "min_norm": 0.25, "max_norm": 16.0, "max_valid_norm": 64.0, "fractional_bits": 14,
        "clip_bits": 8, "direction_check": True, "direction_subset": "secret"}}}
    rng = np.random.default_rng(0)
    deltas = [rng.normal(size=6) * 0.1 for _ in range(3)]
    rounds = {1: ([0, 1, 2], deltas, [False, False, True], [10, 10, 10])}
    globals_ = {0: np.zeros(6), 1: np.mean(deltas, axis=0)}
    missing = _round_rows(rounds, globals_, config)
    assert missing[0]["reference_kind"] == "robust_reference_unavailable"
    recorded = _round_rows(rounds, globals_, config,
                           directions={1: np.array([2, 0, 1, 2, 3])})
    assert recorded[0]["reference_kind"] == "robust_reference"


def test_m3_cohorts_are_large_enough_for_an_honest_majority():
    from fl_security.attacks.byzantine import ByzantineAttacker
    from fl_security.mtd.client_selection import select_clients

    runs = STUDIES["m3"]()
    assert len(runs) == 4 * 4 * 3
    for run in runs:
        fl = run.config["federated_learning"]
        k = len(select_clients(fl["num_clients"], fl["fraction_train"], strategy="fixed"))
        assert k == 7
        attacks = run.config["attacks"]
        if attacks.get("enabled") and "adversary_model" not in attacks:
            assert 2 * attacks["num_malicious"] + 1 <= k
            stratified = ByzantineAttacker(run.config, fl["num_clients"]).malicious_clients
            assert len(stratified & set(range(k))) == 2
    jit = [r for r in runs if r.attack.endswith("__jit4")]
    assert len(jit) == 12 and all(r.config["attacks"]["num_malicious"] == 4 for r in jit)


def test_m1_grid_covers_the_planned_conditions():
    runs = STUDIES["m1"]()
    assert len(runs) == 7 * 5 * 2
    assert CONFIGS["reference_direction_secret"][1]["defences"]["norm_defence_reference"][
        "direction_subset"] == "secret"
    assert all(run.config["attacks"].get("attack_type") != "evasive_backdoor"
               or run.config["attacks"]["evasion_guess_fraction"] == 0.25 for run in runs)
