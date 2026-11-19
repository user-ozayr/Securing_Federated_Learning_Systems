from __future__ import annotations

import csv
import urllib.error
import urllib.request
from collections import UserDict
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from fl_security.evaluation.csv_safety import sanitize_csv_dataframe
from fl_security.evaluation.metrics import ExperimentLogger
from fl_security.federated.flower_simulation import _resolve_authenticated_client_ids
from fl_security.mtd.controller import MTDController
from fl_security.mtd.randomness import HMACCounterRNG
from fl_security.smpc.transport import (
    _SecureRedirectHandler,
    validate_transport_url,
)
from fl_security.config import validate_config


def test_hmac_counter_rng_is_reproducible_and_samples_without_replacement():
    key = b"unit-test-key-material-32-bytes!!"
    left = HMACCounterRNG(key)
    right = HMACCounterRNG(key)

    assert left.sample(range(100), 30) == right.sample(range(100), 30)

    rng = HMACCounterRNG(key)
    selected = rng.sample(range(20), 20)
    assert sorted(selected) == list(range(20))


def test_mtd_controller_uses_secret_keyed_schedule(monkeypatch):
    config = {
        "experiment": {"seed": 123, "rounds": 3},
        "federated_learning": {"num_clients": 10},
        "mtd": {"enabled": True, "selection_strategy": "random"},
    }
    monkeypatch.setenv("FL_MTD_SECRET", "s" * 32)
    first = MTDController(config)
    second = MTDController(config)

    first_round = first.generate_round_config(1, num_clients=10, fraction=0.6)
    second_round = second.generate_round_config(1, num_clients=10, fraction=0.6)

    assert first.secret_seeded is True
    assert first_round["secret_seeded"] is True
    assert first_round["selected_clients"] == second_round["selected_clients"]


def test_mtd_controller_rejects_short_deployment_secret(monkeypatch):
    monkeypatch.setenv("FL_MTD_SECRET", "too-short")
    with pytest.raises(ValueError, match="at least 32 bytes"):
        MTDController({"experiment": {"seed": 1}, "mtd": {}})



def test_different_mtd_secrets_can_change_the_selected_cohort(monkeypatch):
    config = {
        "experiment": {"seed": 42},
        "federated_learning": {"num_clients": 20},
        "mtd": {
            "enabled": True,
            "selection_strategy": "random",
            "change_every_round": True,
        },
        "smpc": {
            "enabled": True,
            "backend": "mp_spdz_spdz2k",
            "num_aggregation_parties": 3,
            "min_clients_per_round": 2,
        },
    }
    monkeypatch.setenv("FL_MTD_SECRET", "a" * 32)
    first = MTDController(config).generate_round_config(4, 20, 0.5)
    monkeypatch.setenv("FL_MTD_SECRET", "b" * 32)
    second = MTDController(config).generate_round_config(4, 20, 0.5)

    assert first["secret_seeded"] and second["secret_seeded"]
    assert first["selected_clients"] != second["selected_clients"]


def test_missing_mtd_secret_is_public_seed_deterministic(monkeypatch):
    monkeypatch.delenv("FL_MTD_SECRET", raising=False)
    config = {
        "experiment": {"seed": 42},
        "federated_learning": {"num_clients": 20},
        "mtd": {
            "enabled": True,
            "selection_strategy": "random",
            "change_every_round": True,
        },
    }
    first = MTDController(config).generate_round_config(4, 20, 0.5)
    repeated = MTDController(config).generate_round_config(4, 20, 0.5)

    assert first["secret_seeded"] is False
    assert repeated["secret_seeded"] is False
    assert first["selected_clients"] == repeated["selected_clients"]


def test_aggregator_transport_requires_https_except_loopback():
    assert validate_transport_url("https://party.example.org") == "https://party.example.org"
    assert validate_transport_url("http://127.0.0.1:8700") == "http://127.0.0.1:8700"
    assert validate_transport_url("http://[::1]:8700") == "http://[::1]:8700"
    assert validate_transport_url("http://localhost:8700") == "http://localhost:8700"
    for url in (
        "http://party.example.org",
        "http://192.0.2.10:8700",
        "ftp://party.example.org",
    ):
        with pytest.raises(ValueError, match="HTTPS"):
            validate_transport_url(url)
    with pytest.raises(ValueError, match="embedded credentials"):
        validate_transport_url("https://user:password@party.example.org")
    request = urllib.request.Request("https://party.example.org/round")
    with pytest.raises(urllib.error.URLError, match="cannot downgrade"):
        _SecureRedirectHandler().redirect_request(
            request, None, 302, "Found", {}, "http://party.example.org/round"
        )


def test_flower_result_identity_must_match_registered_proxy():
    results = [
        (SimpleNamespace(cid="proxy-a"), SimpleNamespace(metrics=UserDict({"client_id": 0}))),
        (SimpleNamespace(cid="proxy-b"), SimpleNamespace(metrics=UserDict({"client_id": 1}))),
    ]
    assert _resolve_authenticated_client_ids(
        results, {0: "proxy-a", 1: "proxy-b"}, [0, 1]
    ) == [0, 1]

    spoofed = [
        (SimpleNamespace(cid="proxy-a"), SimpleNamespace(metrics={"client_id": 1}))
    ]
    with pytest.raises(RuntimeError, match="does not match"):
        _resolve_authenticated_client_ids(spoofed, {0: "proxy-a"}, [0])


def test_flower_rejects_unregistered_or_unselected_proxy_results():
    result = [
        (SimpleNamespace(cid="unknown-proxy"), SimpleNamespace(metrics={"client_id": 0}))
    ]
    with pytest.raises(RuntimeError, match="unregistered proxy"):
        _resolve_authenticated_client_ids(result, {0: "proxy-a"}, [0])

    unselected = [
        (SimpleNamespace(cid="proxy-a"), SimpleNamespace(metrics={"client_id": 0}))
    ]
    with pytest.raises(RuntimeError, match="not selected"):
        _resolve_authenticated_client_ids(unselected, {0: "proxy-a"}, [1])

    duplicate = [unselected[0], unselected[0]]
    with pytest.raises(RuntimeError, match="duplicate results"):
        _resolve_authenticated_client_ids(duplicate, {0: "proxy-a"}, [0])


def test_csv_sanitizer_neutralizes_formula_like_text_but_preserves_numbers():
    frame = pd.DataFrame({
        "text": ["=1+1", "  +SUM(A1:A2)", "\t=HYPERLINK(\"x\")", "normal"],
        "number": [-1, 2, 3, 4],
    })
    safe = sanitize_csv_dataframe(frame)

    assert safe["text"].tolist() == [
        "'=1+1",
        "'  +SUM(A1:A2)",
        "'\t=HYPERLINK(\"x\")",
        "normal",
    ]
    assert safe["number"].tolist() == [-1, 2, 3, 4]


def test_experiment_logger_rejects_traversal_and_writes_plain_csv(tmp_path: Path):
    logger = ExperimentLogger(tmp_path)
    logger.log_round({
        "round": 1,
        "global_accuracy": 0.5,
        "label": "=HYPERLINK(\"https://example.invalid\")",
    })

    with pytest.raises(ValueError, match="single"):
        logger.save_to_csv("../outside.csv")
    with pytest.raises(ValueError, match="single"):
        logger.save_to_csv("nested/outside.csv")
    with pytest.raises(ValueError, match="single"):
        logger.save_to_csv("C:outside.csv")

    outside = tmp_path.parent / "symlink-target.csv"
    outside.write_text("do not overwrite", encoding="utf-8")
    (tmp_path / "linked.csv").symlink_to(outside)
    with pytest.raises(ValueError, match="output_dir"):
        logger.save_to_csv("linked.csv")

    logger.save_to_csv("safe.csv")
    with (tmp_path / "safe.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["label"].startswith("'=")
    assert not (tmp_path.parent / "outside.csv").exists()


def test_experiment_logger_rejects_traversal_plot_filename(tmp_path: Path):
    logger = ExperimentLogger(tmp_path)
    logger.log_round({"round": 1, "global_accuracy": 0.5})
    with pytest.raises(ValueError, match="single"):
        logger.plot_metrics("../outside.png")


def test_configuration_validation_uses_exceptions_for_invalid_input():
    with pytest.raises(ValueError, match="root"):
        validate_config(None)


def test_client_selection_remains_fixed_when_mtd_is_disabled():
    config = {
        "experiment": {"seed": 123},
        "federated_learning": {"num_clients": 10},
        "mtd": {"enabled": False},
        "smpc": {
            "enabled": True,
            "backend": "mp_spdz_spdz2k",
            "num_aggregation_parties": 5,
            "min_clients_per_round": 2,
        },
    }
    controller = MTDController(config)

    first = controller.generate_round_config(1, num_clients=10, fraction=0.6)
    second = controller.generate_round_config(2, num_clients=10, fraction=0.6)

    assert first["selected_clients"] == second["selected_clients"]
    assert "committees" not in first
