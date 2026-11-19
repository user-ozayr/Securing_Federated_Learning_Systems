import json
import os
from dataclasses import replace
from types import SimpleNamespace

import flwr.simulation
import pandas as pd
import pytest
import torch
from flwr.common import parameters_to_ndarrays
from torch.utils.data import TensorDataset

import fl_security.federated.flower_simulation as flower_runner


def test_flower_strategy_uses_active_spdz2k_and_aborts_on_client_mismatch(
    monkeypatch, tmp_path
):
    """Exercise Flower's secure client/strategy path without starting MPC processes."""
    torch.set_num_threads(1)
    images = torch.randn(6, 3, 32, 32)
    labels = torch.tensor([0, 1, 0, 1, 0, 1], dtype=torch.long)
    trainset = TensorDataset(images, labels)
    testset = TensorDataset(images[:4], labels[:4])
    client_partitions = [
        TensorDataset(images[offset:offset + 2], labels[offset:offset + 2])
        for offset in (0, 2, 4)
    ]
    monkeypatch.setattr(
        flower_runner, "load_cifar10_data", lambda: (trainset, testset)
    )
    monkeypatch.setattr(
        flower_runner, "partition_data", lambda *args, **kwargs: client_partitions
    )

    parties = [
        SimpleNamespace(client_host=f"127.0.0.{party_id + 1}")
        for party_id in range(3)
    ]
    monkeypatch.setattr(
        flower_runner, "load_party_configuration", lambda count: parties
    )
    monkeypatch.setattr(flower_runner, "client_port_base", lambda: 21_000)
    monkeypatch.setenv("FL_MPSPDZ_HOME", "test-mp-spdz")
    monkeypatch.setenv("FL_MPSPDZ_CLIENT_CREDENTIALS_DIR", str(tmp_path))
    monkeypatch.setenv("FL_MPSPDZ_PARTIES_JSON", '{"coordinator-secret":"hidden"}')
    monkeypatch.setenv("FL_MPSPDZ_CONTROL_TOKEN", "party-control-secret-" + ("x" * 32))
    monkeypatch.setenv("FL_MTD_SECRET", "mtd-secret-for-test-" + ("x" * 32))

    submitted = {}
    round_calls = []
    abort_calls = []

    def fake_submit(state, num_examples, client_id, **kwargs):
        submitted[client_id] = (
            {key: value.detach().cpu().clone() for key, value in state.items()},
            num_examples,
        )
        return sum(value.numel() for value in state.values()) * 8

    def fake_receive(global_state, *, expected_total_examples, **kwargs):
        assert expected_total_examples == sum(
            count for _, count in submitted.values()
        )
        result = {}
        for key, base in global_state.items():
            if torch.is_floating_point(base):
                result[key] = sum(
                    (state[key] * count for state, count in submitted.values()),
                    torch.zeros_like(base),
                ) / expected_total_examples
            else:
                result[key] = base.detach().clone()
        return result

    monkeypatch.setattr(
        flower_runner, "start_round", lambda *args: round_calls.append(args)
    )
    monkeypatch.setattr(
        flower_runner, "check_round_running", lambda *args: None
    )
    monkeypatch.setattr(flower_runner, "submit_client_update", fake_submit)
    monkeypatch.setattr(
        flower_runner, "receive_weighted_average", fake_receive
    )
    monkeypatch.setattr(flower_runner, "finish_round", lambda *args: None)
    monkeypatch.setattr(
        flower_runner, "abort_round", lambda *args: abort_calls.append(args)
    )

    def deterministic_flower_scheduler(
        client_fn, num_clients, config, strategy, **kwargs
    ):
        assert "FL_MPSPDZ_PARTIES_JSON" not in os.environ
        assert "FL_MPSPDZ_CONTROL_TOKEN" not in os.environ
        assert "FL_MTD_SECRET" not in os.environ
        proxies = {
            str(cid): SimpleNamespace(cid=str(cid)) for cid in range(num_clients)
        }
        client_manager = SimpleNamespace(all=lambda: proxies)
        parameters = strategy.initialize_parameters(client_manager)

        for server_round in range(1, config.num_rounds + 1):
            instructions = strategy.configure_fit(
                server_round, parameters, client_manager
            )
            results = []
            for proxy, fit_ins in instructions:
                assert "local_client_tokens_json" not in fit_ins.config
                assert json.loads(fit_ins.config["mp_spdz_client_hosts_json"]) == [
                    party.client_host for party in parties
                ]
                client = client_fn(proxy.cid)
                fit_res = client.fit(fit_ins)
                assert parameters_to_ndarrays(fit_res.parameters) == []
                assert fit_res.metrics["mp_spdz_input_submitted"] == 1
                results.append((proxy, fit_res))

            parameters, fit_metrics = strategy.aggregate_fit(
                server_round, results, []
            )
            assert parameters is not None
            assert fit_metrics["smpc_enabled"] == 1
            assert fit_metrics["selected_clients"] == 3
            assert fit_metrics["mp_spdz_parties_used"] == 3

            loss, evaluation_metrics = strategy.evaluate(server_round, parameters)
            assert loss >= 0
            assert 0.0 <= evaluation_metrics["accuracy"] <= 1.0

            forged_results = [
                (proxy, replace(fit_res, num_examples=fit_res.num_examples + 1))
                if index == 0 else (proxy, fit_res)
                for index, (proxy, fit_res) in enumerate(results)
            ]
            with pytest.raises(RuntimeError, match="example counts"):
                strategy.aggregate_fit(server_round, forged_results, [])
            with pytest.raises(RuntimeError, match="selected client did not complete"):
                strategy.aggregate_fit(server_round, results[:-1], [])

        return None

    monkeypatch.setattr(
        flwr.simulation, "start_simulation", deterministic_flower_scheduler
    )
    config = {
        "experiment": {"name": "flower_secure_smoke", "seed": 123, "rounds": 1},
        "federated_learning": {
            "framework": "flower",
            "dataset": "cifar10",
            "num_clients": 3,
            "fraction_train": 1.0,
            "local_epochs": 1,
            "batch_size": 2,
            "learning_rate": 0.001,
            "partitioning": "iid",
        },
        "mtd": {
            "enabled": True,
            "selection_strategy": "random",
            "change_every_round": True,
        },
        "smpc": {
            "enabled": True,
            "backend": "mp_spdz_spdz2k",
            "fixed_point_scale": 100_000,
            "num_aggregation_parties": 3,
            "min_clients_per_round": 2,
        },
        "attacks": {
            "enabled": False,
            "attack_type": "sign_flip",
            "compromised_fraction": 0.0,
            "strength": 1.0,
        },
        "evaluation": {
            "output_dir": str(tmp_path),
            "save_csv": True,
            "save_plots": False,
        },
    }

    flower_runner.run_flower_simulation(config)
    assert len(round_calls) == 1
    assert len(submitted) == 3
    assert len(abort_calls) == 2
    assert os.environ["FL_MTD_SECRET"].startswith("mtd-secret-for-test-")
    assert os.environ["FL_MPSPDZ_CONTROL_TOKEN"].startswith(
        "party-control-secret-"
    )

    results = pd.read_csv(tmp_path / "flower_secure_smoke_results.csv")
    assert len(results) == 1
    assert results.loc[0, "smpc_enabled"] == 1
    assert results.loc[0, "selected_clients"] == 3
    assert results.loc[0, "completed_clients"] == 3
    assert results.loc[0, "mp_spdz_input_bytes"] > 0
