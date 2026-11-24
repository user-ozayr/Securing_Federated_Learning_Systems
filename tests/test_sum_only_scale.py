"""Check that the power-of-two sum-only scale matches plaintext FedAvg where expected."""
import pytest
import torch

from fl_security.experiments.grid import CONFIGS, SMPC, SMPC_SUM_ONLY
from fl_security.federated.aggregation import weighted_fedavg
from fl_security.smpc.fixed_point import FixedPointEncoder
from fl_security.smpc.mp_spdz import _encode_weighted_model

SCALE = 1 << 40


def _emulate_sum_only_aggregate(states, counts, scale, max_clients=12):
    """Integer arithmetic of the sum-only round: encode n*w, add, divide by S and N."""
    encoder = FixedPointEncoder(scale)
    total = None
    layout = None
    for state, n in zip(states, counts):
        values, layout = _encode_weighted_model(state, n, encoder, max_clients)
        total = values if total is None else [a + b for a, b in zip(total, values)]
    result, offset = {}, 0
    for key, shape in layout:
        size = torch.Size(shape).numel()
        weighted = torch.tensor(total[offset:offset + size], dtype=torch.float64).reshape(shape)
        result[key] = (weighted / scale / total[-1]).to(torch.float32)
        offset += size
    return result


def _make_client_states(seed, clients=4, size=2202):
    generator = torch.Generator().manual_seed(seed)
    states = []
    for _ in range(clients):
        w = torch.randn(size, generator=generator) * 0.3
        # Keep |w| at or above 1e-4, where n * w * 2^40 is an exact integer.
        w = torch.where(w.abs() < 1e-4, torch.full_like(w, 1e-4), w).to(torch.float32)
        states.append({"w": w})
    return states


def test_sum_only_conditions_use_power_of_two_scale():
    assert SMPC_SUM_ONLY["fixed_point_scale"] == SCALE
    for name in ("smpc_only", "smpc_mtd"):
        assert CONFIGS[name][1]["smpc"]["fixed_point_scale"] == SCALE


def test_robust_conditions_keep_their_recorded_configuration():
    # The robust program uses 2^f. Keep its recorded configuration unchanged.
    for name in ("smpc_clip", "smpc_defence_mtd"):
        assert CONFIGS[name][1]["smpc"]["fixed_point_scale"] == SMPC["fixed_point_scale"]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_power_of_two_scale_reproduces_fedavg_bitwise(seed):
    states = _make_client_states(seed)
    counts = [5000] * 4
    fedavg = weighted_fedavg(states, counts, {"w": torch.zeros(2202)})["w"]
    secure = _emulate_sum_only_aggregate(states, counts, SCALE)["w"]
    assert torch.equal(secure, fedavg)


def test_decimal_scale_can_differ_from_fedavg():
    differs = 0
    for seed in range(1, 6):
        states = _make_client_states(seed)
        fedavg = weighted_fedavg(states, [5000] * 4, {"w": torch.zeros(2202)})["w"]
        decimal = _emulate_sum_only_aggregate(states, [5000] * 4, 1_000_000)["w"]
        assert torch.allclose(decimal, fedavg, atol=1e-6)
        differs += int((decimal != fedavg).sum())
    assert differs > 0


def test_ring_guard_admits_healthy_weights_and_rejects_diverged_ones():
    encoder = FixedPointEncoder(SCALE)
    _encode_weighted_model({"w": torch.full((3,), 60.0)}, 5000, encoder, 12)
    with pytest.raises(OverflowError):
        _encode_weighted_model({"w": torch.full((3,), 80.0)}, 5000, encoder, 12)
