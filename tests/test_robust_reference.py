"""Exact-arithmetic tests for the robust SPDZ2k aggregation reference."""
import math
import random

import pytest
import torch

from fl_security.smpc.robust import (
    RING_MODULUS,
    SecureDefenceConfig,
    _lt,
    apply_delta,
    chunked_wire_values,
    decode_robust_output,
    encode_delta,
    robust_reference,
    round_arguments,
    to_signed,
    validate_spec,
)


def _vector(norm, dimension, scale, rng):
    raw = [rng.gauss(0.0, 1.0) for _ in range(dimension)]
    length = math.sqrt(sum(v * v for v in raw))
    return [int(round(norm * v / length * scale)) for v in raw]


def _run(config, rows, counts=None):
    counts = counts or [100] * len(rows)
    weights = config.quantized_weights(counts)
    spec = config.round_spec(weights)
    result = robust_reference(rows, weights, spec)
    return weights, result, decode_robust_output(result, weights, config)


def test_comparison_emulates_signed_64_bit_difference():
    assert _lt(1, 2) == 1 and _lt(2, 1) == 0 and _lt(5, 5) == 0
    assert _lt(-3 % RING_MODULUS, 0) == 1
    # Out-of-range operands: (2^63 - 1) - (-1) = 2^63 wraps to -2^63, so MP-SPDZ
    # reports "2^63 - 1 < -1". Comparisons are only meaningful for |a - b| < 2^63,
    # which the bit budget guarantees for honest inputs.
    assert _lt((1 << 63) - 1, RING_MODULUS - 1) == 1
    assert to_signed((1 << 63)) == -(1 << 63)


def test_static_clipping_matches_floating_point_reference():
    rng = random.Random(1)
    config = SecureDefenceConfig(mode="clip", threshold="static", static_norm=1.0, clip_bits=8)
    norms = [0.3, 0.8, 2.5, 25.0]
    rows = [_vector(n, 64, config.scale, rng) for n in norms]
    _, result, decoded = _run(config, rows)
    assert result.accepted == [1, 1, 1, 1]
    assert result.clip_flags == [0, 0, 1, 1]
    # coefficients are floor(2^g * min(1, tau / ||x||)): conservative clipping
    for row, coefficient in zip(rows, result.coefficients):
        norm = math.sqrt(sum(v * v for v in row)) / config.scale
        exact = 256 * min(1.0, 1.0 / norm)
        assert coefficient <= exact + 1e-9 and coefficient > exact - 1 - 1e-9
    ideal = [0.0] * 64
    for row in rows:
        values = [v / config.scale for v in row]
        norm = math.sqrt(sum(v * v for v in values))
        factor = min(1.0, 1.0 / norm)
        ideal = [a + factor * v / 4 for a, v in zip(ideal, values)]
    error = max(abs(a - b) for a, b in zip(decoded.delta.tolist(), ideal))
    assert error < 0.02
    assert decoded.output_check_passed
    assert decoded.aggregate_norm <= 1.0


def test_adaptive_threshold_uses_lower_median_and_clamps():
    rng = random.Random(2)
    config = SecureDefenceConfig(mode="clip_screen", threshold="adaptive", min_norm=0.05,
                                 max_norm=4.0, screen_multiplier_squared=4)
    rows = [_vector(n, 32, config.scale, rng) for n in (0.4, 0.5, 0.6, 10.0)]
    _, result, decoded = _run(config, rows)
    assert abs(decoded.threshold_norm - 0.5) < 1e-3
    assert result.accepted == [1, 1, 1, 0]          # The value 10 exceeds twice the 0.5 threshold, so it is rejected.
    assert result.clip_flags == [0, 0, 1, 0]        # The value 0.6 is above the 0.5 threshold, so it is clipped.
    # Clamp to max_norm when every honest update norm is large.
    rows = [_vector(n, 32, config.scale, rng) for n in (20.0, 21.0, 22.0, 23.0)]
    _, result, decoded = _run(config, rows)
    assert abs(decoded.threshold_norm - 4.0) < 1e-3


def test_screen_only_does_not_scale_accepted_updates():
    rng = random.Random(3)
    config = SecureDefenceConfig(mode="screen", threshold="adaptive", screen_multiplier_squared=4,
                                 min_norm=0.05, max_norm=4.0)
    rows = [_vector(n, 16, config.scale, rng) for n in (0.4, 0.5, 0.9, 9.0)]
    _, result, decoded = _run(config, rows)
    assert result.accepted == [1, 1, 1, 0]
    assert result.coefficients == [64, 64, 64, 64]
    assert decoded.output_check_passed


def test_zero_and_boundary_updates():
    rng = random.Random(4)
    config = SecureDefenceConfig(mode="clip", threshold="static", static_norm=1.0)
    rows = [[0] * 16, _vector(1.0, 16, config.scale, rng), _vector(1e-4, 16, config.scale, rng)]
    _, result, decoded = _run(config, rows)
    assert result.accepted == [1, 1, 1]
    assert result.coefficients[0] == 64
    assert decoded.output_check_passed


def test_out_of_range_and_negative_square_inputs_are_excluded():
    rng = random.Random(5)
    config = SecureDefenceConfig(mode="clip", threshold="static", static_norm=1.0)
    honest = [_vector(0.5, 16, config.scale, rng) for _ in range(3)]
    big = [0] * 16
    big[0] = 1 << 27                       # ||x||^2 = 2^54 > r_max, so no wrap occurs.
    negative = [0] * 16
    negative[0] = 3 << 30                  # ||x||^2 = 2^63 + 2^60, which is negative modulo 2^64.
    _, result, decoded = _run(config, honest + [big])
    assert result.accepted == [1, 1, 1, 0] and decoded.output_check_passed
    _, result, decoded = _run(config, honest + [negative])
    assert result.accepted == [1, 1, 1, 0] and decoded.output_check_passed


def test_wraparound_input_passes_mpc_check_but_fails_output_check():
    rng = random.Random(6)
    config = SecureDefenceConfig(mode="clip", threshold="static", static_norm=1.0)
    honest = [_vector(0.5, 16, config.scale, rng) for _ in range(3)]
    wrap = _vector(0.2, 16, config.scale, rng)
    wrap[0] = 1 << 32                      # This value squares to 0 modulo 2^64.
    _, result, decoded = _run(config, honest + [wrap])
    assert result.accepted == [1, 1, 1, 1]
    assert not decoded.output_check_passed


def test_inverse_weight_attack_is_bounded_by_visible_norm():
    rng = random.Random(7)
    config = SecureDefenceConfig(mode="clip", threshold="static", static_norm=1.0,
                                 weighting="sample", weight_bits=3)
    counts = [3000, 3000, 3000, 1000]
    weights = config.quantized_weights(counts)
    assert weights[3] % 2 == 1
    target = _vector(5.0, 16, config.scale, rng)
    inverse = pow(weights[3], -1, RING_MODULUS)
    crafted = [(v * inverse) % RING_MODULUS for v in target]
    rows = [_vector(0.5, 16, config.scale, rng) for _ in range(3)] + [crafted]
    _, result, decoded = _run(config, rows, counts)
    # The visible contribution C*w*x = C*D has norm C*||D||/2^g; an honest client
    # with weight w may contribute at most w*tau. The attack gains nothing more.
    contribution = result.coefficients[3] * 5.0 / 64.0
    assert result.clip_flags[3] == 1
    assert contribution <= weights[3] * 1.0 + 1e-6
    assert contribution > 0.9 * weights[3]
    assert decoded.output_check_passed


def test_budget_validation_rejects_overflowing_parameters():
    with pytest.raises(ValueError):
        SecureDefenceConfig(mode="clip", fractional_bits=20, clip_bits=16,
                            max_valid_norm=4096.0, max_norm=4096.0).round_spec([1, 1])
    with pytest.raises(ValueError):
        validate_spec([1, 0, 0, 10, 1, 10, 1, 4, 8, 1 << 62, 0, 0, 0], [1, 1])
    with pytest.raises(ValueError):
        validate_spec([0, 0, 0, 10, 1, 10, 1, 4, 8, 100, 0, 0, 0], [1, 1])
    with pytest.raises(ValueError):
        SecureDefenceConfig(mode="unknown")
    with pytest.raises(ValueError):
        SecureDefenceConfig.from_mapping({"enabled": True, "surprise": 1})


def test_quantized_weights_uniform_sample_and_gcd():
    config = SecureDefenceConfig()
    assert config.quantized_weights([10, 20, 30]) == [1, 1, 1]
    sample = SecureDefenceConfig(weighting="sample", weight_bits=3)
    assert sample.quantized_weights([1000, 2000, 3000, 6000]) == [1, 3, 4, 8]
    assert sample.quantized_weights([5000, 5000]) == [1, 1]


def test_round_arguments_sort_clients_and_align_counts_and_weights():
    args = round_arguments([5, 2, 9], [50, 20, 90], [3, 1, 2], 11, 12, 20000, 256, [1] * 13)
    assert args[:3] == ["2,5,9", "20,50,90", "1,3,2"]
    assert args[3:7] == ["11", "12", "20000", "256"]


def test_encode_apply_and_wire_format_roundtrip():
    base = {"w": torch.zeros(3), "b": torch.tensor([1.0]), "steps": torch.tensor(7)}
    local = {"w": torch.tensor([0.5, -0.25, 1e-5]), "b": torch.tensor([1.5]), "steps": torch.tensor(9)}
    encoded = encode_delta(local, base, 14)
    assert encoded == [8192, -4096, 0, 8192]
    wire = chunked_wire_values(40, encoded, 16)
    assert wire[0] == 40 and len(wire) == 16 and wire[5:] == [0] * 11
    updated = apply_delta(base, torch.tensor(encoded, dtype=torch.float64) / 16384)
    assert torch.allclose(updated["w"], torch.tensor([0.5, -0.25, 0.0]))
    assert torch.equal(updated["steps"], torch.tensor(7))
    with pytest.raises(ValueError):
        encode_delta({"w": torch.tensor([float("nan"), 0, 0]), "b": torch.tensor([1.0]),
                      "steps": torch.tensor(1)}, base, 14)
