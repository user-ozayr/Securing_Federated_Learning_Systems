"""Flower strategy with the robust SPDZ2k program, MPC calls replaced by the reference."""
import json
from dataclasses import replace
from types import SimpleNamespace

import flwr.simulation
import pandas as pd
import pytest
import torch
from flwr.common import parameters_to_ndarrays
from torch.utils.data import TensorDataset

import fl_security.federated.flower_simulation as flower_runner
from fl_security.smpc.robust import (
    SecureDefenceConfig,
    decode_robust_output,
    encode_delta,
    robust_reference,
)


def test_simulation_abort_keeps_completed_rounds_and_reraises(monkeypatch, tmp_path):
    torch.set_num_threads(1)
    images = torch.randn(8, 1, 28, 28, generator=torch.Generator().manual_seed(1))
    labels = torch.arange(8) % 10
    data = TensorDataset(images, labels)
    monkeypatch.setattr(flower_runner, "load_dataset", lambda name, root=None: (data, data))
    monkeypatch.setattr(flower_runner, "partition_data",
                        lambda *a, **k: [TensorDataset(images[i * 4:(i + 1) * 4], labels[i * 4:(i + 1) * 4])
                                         for i in range(2)])
    monkeypatch.delenv("FL_MTD_SECRET", raising=False)

    def scheduler(client_fn, num_clients, config, strategy, **kwargs):
        proxies = {str(cid): SimpleNamespace(cid=str(cid)) for cid in range(num_clients)}
        manager = SimpleNamespace(all=lambda: proxies)
        parameters = strategy.initialize_parameters(manager)
        strategy.evaluate(0, parameters)
        instructions = strategy.configure_fit(1, parameters, manager)
        results = [(proxy, client_fn(proxy.cid).fit(ins)) for proxy, ins in instructions]
        parameters, _ = strategy.aggregate_fit(1, results, [])
        strategy.evaluate(1, parameters)
        try:
            raise OverflowError("weighted model tensor exceeds the safe SPDZ2k ring range")
        except OverflowError as exc:
            raise RuntimeError("Simulation crashed.") from exc

    monkeypatch.setattr(flwr.simulation, "start_simulation", scheduler)
    config = {
        "experiment": {"name": "abort_path", "seed": 3, "rounds": 5},
        "federated_learning": {"framework": "flower", "dataset": "fashion_mnist", "model": "compact_cnn",
                               "num_clients": 2, "fraction_train": 1.0, "local_epochs": 1,
                               "batch_size": 2, "learning_rate": 0.01, "partitioning": "iid"},
        "mtd": {"schedule": "static"},
        "smpc": {"enabled": False},
        "attacks": {"enabled": False},
        "evaluation": {"output_dir": str(tmp_path), "save_csv": True, "save_plots": False},
    }
    with pytest.raises(RuntimeError, match="Simulation crashed"):
        flower_runner.run_flower_simulation(config)
    frame = pd.read_csv(tmp_path / "abort_path_results.csv")
    assert list(frame["round"]) == [0, 1]
    abort = json.loads((tmp_path / "abort_path_abort.json").read_text())
    assert abort["rounds_completed"] == 1 and abort["rounds_configured"] == 5
    assert abort["cause_type"] == "OverflowError"


def test_robust_strategy_applies_reference_decoded_update(monkeypatch, tmp_path):
    torch.set_num_threads(1)
    generator = torch.Generator().manual_seed(0)
    images = torch.randn(16, 1, 28, 28, generator=generator)
    labels = torch.arange(16) % 10
    trainset = TensorDataset(images, labels)
    testset = TensorDataset(images[:8], labels[:8])
    partitions = [TensorDataset(images[i * 4:(i + 1) * 4], labels[i * 4:(i + 1) * 4]) for i in range(4)]
    monkeypatch.setattr(flower_runner, "load_dataset", lambda name, root=None: (trainset, testset))
    monkeypatch.setattr(flower_runner, "partition_data", lambda *a, **k: partitions)
    parties = [SimpleNamespace(client_host="127.0.0.1", party_id=i) for i in range(3)]
    monkeypatch.setattr(flower_runner, "load_party_configuration", lambda count: parties)
    monkeypatch.setattr(flower_runner, "client_port_base", lambda: 21_000)
    monkeypatch.setenv("FL_MPSPDZ_HOME", "test-mp-spdz")
    monkeypatch.setenv("FL_MPSPDZ_CLIENT_CREDENTIALS_DIR", str(tmp_path))
    monkeypatch.delenv("FL_MTD_SECRET", raising=False)

    defence = {"enabled": True, "mode": "clip_screen", "threshold": "adaptive",
               "screen_multiplier_squared": 4, "min_norm": 0.01, "max_norm": 16.0,
               "max_valid_norm": 64.0, "clip_bits": 8}
    defence_config = SecureDefenceConfig.from_mapping(defence)
    started, submitted, applied = [], {}, []

    def fake_start(*args, **kwargs):
        started.append((args, kwargs))

    def fake_submit(local_state, global_state, num_examples, client_id, **kwargs):
        assert kwargs["fractional_bits"] == 14 and kwargs["chunk_size"] == 256
        submitted[client_id] = encode_delta(local_state, global_state, 14)
        return 8

    def fake_receive(*, client_count, dimension, **kwargs):
        ids = sorted(submitted)
        assert len(ids) == client_count and dimension == 2202
        weights = [1] * client_count
        result = robust_reference([submitted[i] for i in ids], weights,
                                  defence_config.round_spec(weights))
        applied.append(decode_robust_output(result, weights, defence_config))
        return result

    monkeypatch.setattr(flower_runner, "start_round", fake_start)
    monkeypatch.setattr(flower_runner, "check_round_running", lambda *a: None)
    monkeypatch.setattr(flower_runner, "submit_client_delta", fake_submit)
    monkeypatch.setattr(flower_runner, "receive_robust_result", fake_receive)
    monkeypatch.setattr(flower_runner, "finish_round",
                        lambda *a: [{"party_id": 0, "protocol_seconds": 1.5, "global_data_sent_mb": 9.0}])
    aborts = []
    monkeypatch.setattr(flower_runner, "abort_round", lambda *a: aborts.append(a))

    def scheduler(client_fn, num_clients, config, strategy, **kwargs):
        proxies = {str(cid): SimpleNamespace(cid=str(cid)) for cid in range(num_clients)}
        manager = SimpleNamespace(all=lambda: proxies)
        parameters = strategy.initialize_parameters(manager)
        before = [a.copy() for a in parameters_to_ndarrays(parameters)]
        instructions = strategy.configure_fit(1, parameters, manager)
        assert all(ins.config["mp_spdz_program"] == "robust_aggregate" for _, ins in instructions)
        results = []
        for proxy, ins in instructions:
            res = client_fn(proxy.cid).fit(ins)
            assert parameters_to_ndarrays(res.parameters) == []
            results.append((proxy, res))
        new_parameters, _ = strategy.aggregate_fit(1, results, [])
        after = parameters_to_ndarrays(new_parameters)
        flat = torch.cat([torch.from_numpy(a - b).reshape(-1).double() for a, b in zip(after, before)])
        assert torch.allclose(flat, applied[0].delta, atol=1e-6)
        strategy.evaluate(1, new_parameters)
        forged = [(results[0][0], replace(results[0][1], num_examples=99))] + results[1:]
        with pytest.raises(RuntimeError, match="example counts"):
            strategy.aggregate_fit(1, forged, [])

    monkeypatch.setattr(flwr.simulation, "start_simulation", scheduler)
    config = {
        "experiment": {"name": "robust_path", "seed": 5, "rounds": 1},
        "federated_learning": {"framework": "flower", "dataset": "fashion_mnist",
                               "model": "compact_cnn", "num_clients": 4, "fraction_train": 1.0,
                               "local_epochs": 1, "batch_size": 2, "learning_rate": 0.01,
                               "partitioning": "iid"},
        "mtd": {"schedule": "deterministic"},
        "smpc": {"enabled": True, "backend": "mp_spdz_spdz2k", "fixed_point_scale": 1_000_000,
                 "num_aggregation_parties": 3, "min_clients_per_round": 2, "defence": defence},
        "attacks": {"enabled": True, "attack_type": "scaled_replacement", "num_malicious": 1,
                    "boost": 50.0},
        "evaluation": {"output_dir": str(tmp_path), "save_csv": True, "save_plots": False},
    }
    flower_runner.run_flower_simulation(config)
    _, kwargs = started[0]
    assert kwargs["program"] == "robust_aggregate"
    assert kwargs["weights"] == [1, 1, 1, 1]
    assert kwargs["robust_spec"] == defence_config.round_spec([1, 1, 1, 1])
    assert len(aborts) == 1
    frame = pd.read_csv(tmp_path / "robust_path_results.csv")
    row = frame.iloc[0]
    assert row["smpc_program"] == "robust_aggregate"
    malicious = json.loads(row["malicious_client_ids"])
    assert len(malicious) == 1
    assert json.loads(row["defence_rejected_client_ids"]) == malicious   # The update scaled by 50 is rejected.
    assert row["rejected_true_positives"] == 1
    assert row["mpc_protocol_seconds_max"] == 1.5
    assert row["defence_output_check_passed"] == 1
