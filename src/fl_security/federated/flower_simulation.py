"""Flower simulation with malicious-secure MP-SPDZ SPDZ2k aggregation."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections.abc import Mapping
from numbers import Integral

import numpy as np
import torch
from torch.utils.data import DataLoader

from fl_security.attacks.byzantine import ByzantineAttacker
from fl_security.evaluation.metrics import ExperimentLogger
from fl_security.federated.aggregation import (
    weighted_fedavg,
)
from fl_security.federated.dataset import load_cifar10_data, partition_data
from fl_security.federated.model import CIFAR10CNN
from fl_security.federated.robust_aggregation import RobustUpdateDetector
from fl_security.federated.training import evaluate_model, train_local
from fl_security.mtd.controller import MTDController
from fl_security.smpc.fixed_point import FixedPointEncoder
from fl_security.smpc.mp_spdz import (
    SPDZ2K_BACKEND,
    SPDZ2K_IO_CHUNK_SIZE,
    abort_round,
    check_round_running,
    client_port_base,
    finish_round,
    load_party_configuration,
    receive_weighted_average,
    start_round,
    submit_client_update,
)

def _resolve_authenticated_client_ids(results, proxy_id_by_client, selected_client_ids):
    """Bind every FitRes identity to its registered Flower proxy.

    The client_id metric is client supplied and is never trusted on its own.
    Flower's registered proxy ID is the simulation/runtime identity anchor.
    """
    if not isinstance(proxy_id_by_client, dict) or not proxy_id_by_client:
        raise RuntimeError("Flower proxy identity map has not been initialized")

    proxy_to_logical = {}
    for logical_id, proxy_id in proxy_id_by_client.items():
        logical = int(logical_id)
        proxy = str(proxy_id)
        if proxy in proxy_to_logical:
            raise RuntimeError("Flower proxy identity map contains duplicate proxies")
        proxy_to_logical[proxy] = logical

    selected = {int(client_id) for client_id in selected_client_ids}
    resolved = []
    seen_logical_ids = set()
    for client_proxy, fit_res in results:
        proxy_id = getattr(client_proxy, "cid", None)
        logical_id = proxy_to_logical.get(str(proxy_id))
        if proxy_id is None or logical_id is None:
            raise RuntimeError("Flower returned a result from an unregistered proxy")
        if logical_id not in selected:
            raise RuntimeError("Flower returned a result from a client not selected this round")
        if logical_id in seen_logical_ids:
            raise RuntimeError("Flower returned duplicate results for one client")
        seen_logical_ids.add(logical_id)

        metrics = getattr(fit_res, "metrics", {})
        reported_id = metrics.get("client_id") if isinstance(metrics, Mapping) else None
        if (
            isinstance(reported_id, bool)
            or not isinstance(reported_id, Integral)
            or int(reported_id) != logical_id
        ):
            raise RuntimeError(
                "Client-reported identity does not match its registered Flower proxy"
            )
        resolved.append(logical_id)

    if len(set(resolved)) != len(resolved):
        raise RuntimeError("Flower returned duplicate client results for a round")
    return resolved

def run_flower_simulation(config: dict) -> None:
    """Run Flower with plaintext FedAvg or the configured active SPDZ2k backend."""
    try:
        from flwr.client import NumPyClient
        from flwr.common import FitIns, ndarrays_to_parameters, parameters_to_ndarrays
        from flwr.server import ServerConfig
        from flwr.server.strategy import Strategy
        from flwr.simulation import start_simulation
    except ImportError as exc:
        raise RuntimeError(
            "Flower simulation dependencies are missing. Install with pip install -e .[simulation]."
        ) from exc

    experiment, fl_config = config["experiment"], config["federated_learning"]
    num_clients, rounds = int(fl_config["num_clients"]), int(experiment["rounds"])
    seed = int(experiment.get("seed", 42))
    torch.manual_seed(seed)
    trainset, testset = load_cifar10_data()
    client_datasets = partition_data(
        trainset, num_clients, fl_config.get("partitioning", "iid"), seed
    )
    testloader = DataLoader(testset, batch_size=64, shuffle=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    attacker, mtd = ByzantineAttacker(config, num_clients), MTDController(config)

    smpc_config = config.get("smpc", {})
    use_smpc = bool(smpc_config.get("enabled", False))
    min_clients = int(smpc_config.get("min_clients_per_round", 2))
    encoder, party_config, party_hosts, mpc_port = None, [], [], None
    mpc_input_count = 0
    robust_config = config.get("defences", {}).get("robust_aggregation", {})
    robust_enabled = bool(robust_config.get("enabled", False))
    if use_smpc and robust_enabled:
        raise ValueError(
            "Individual-update robust screening is not available with the current "
            "sum-only SMPC backend. Do not enable it until robust scoring and "
            "selection are implemented inside MPC."
        )
    if robust_enabled and num_clients < int(robust_config.get("min_survivors", 2)):
        raise ValueError("robust aggregation requires at least min_survivors clients")

    if use_smpc:
        if smpc_config.get("backend") != SPDZ2K_BACKEND:
            raise RuntimeError(
                f"SMPC is enabled but backend must be exactly {SPDZ2K_BACKEND!r}; "
                "there is no additive-sharing or plaintext fallback"
            )
        party_count = int(smpc_config["num_aggregation_parties"])
        if party_count < 2:
            raise ValueError("SPDZ2k requires at least two aggregation parties")
        encoder = FixedPointEncoder(int(smpc_config.get("fixed_point_scale", 1_000_000)))
        party_config = load_party_configuration(party_count)
        party_hosts = [party.client_host for party in party_config]
        mpc_port = client_port_base()
        if mpc_port + party_count - 1 > 65535:
            raise ValueError("SPDZ2k client port range exceeds TCP port limits")
        if not os.environ.get("FL_MPSPDZ_HOME"):
            raise RuntimeError("FL_MPSPDZ_HOME must be provisioned for SPDZ2k")
        if not os.environ.get("FL_MPSPDZ_CLIENT_CREDENTIALS_DIR"):
            raise RuntimeError(
                "FL_MPSPDZ_CLIENT_CREDENTIALS_DIR must be provisioned for SPDZ2k"
            )
    global_model = CIFAR10CNN()
    initial_state = global_model.state_dict()
    if use_smpc:
        mpc_input_count = sum(
            tensor.numel()
            for tensor in initial_state.values()
            if torch.is_floating_point(tensor)
        ) + 1
    state_keys = list(initial_state)
    initial_arrays = [tensor.detach().cpu().numpy() for tensor in initial_state.values()]
    initial_parameters = ndarrays_to_parameters(initial_arrays)
    logger = ExperimentLogger(output_dir=config.get("evaluation", {}).get("output_dir", "./results"))
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", str(experiment.get("name", "fl")))
    experiment_prefix = f"{slug}-{seed}"

    class ResearchNumPyClient(NumPyClient):
        """Client whose experiment identity is supplied by the server."""

        def __init__(self, flower_cid: str):
            self.flower_cid = str(flower_cid)

        def get_parameters(self, client_config):
            return [array.copy() for array in initial_arrays]

        def fit(self, parameters, fit_config):
            client_id = int(fit_config["client_id"])
            dataset = client_datasets[client_id]
            round_num = int(fit_config["server_round"])

            state = {
                key: torch.from_numpy(array.copy())
                for key, array in zip(state_keys, parameters)
            }
            model = CIFAR10CNN()
            model.load_state_dict(state)
            torch.manual_seed(seed + round_num * 100_000 + client_id)

            loader = DataLoader(
                dataset,
                batch_size=int(fl_config.get("batch_size", 32)),
                shuffle=True,
            )

            label_transform = None
            if attacker.is_malicious(client_id, round_num) and attacker.attack_type == "label_flip":
                def label_transform(labels):
                    values = attacker.perturb_labels(
                        client_id, round_num, labels, num_classes=10
                    )
                    return torch.as_tensor(
                        values, dtype=torch.long, device=labels.device
                    )

            local_state = train_local(
                model,
                loader,
                epochs=int(fl_config.get("local_epochs", 1)),
                lr=float(fl_config.get("learning_rate", 0.01)),
                device=device,
                label_transform=label_transform,
            )

            bad_training = [
                key for key, value in local_state.items()
                if torch.is_floating_point(value)
                and not torch.isfinite(value).all()
            ]

            if bad_training:
                raise RuntimeError(
                    f"Client {client_id}: non-finite values produced "
                    f"during local training in tensors: {bad_training}")
            local_state = attacker.perturb_update(
                client_id, round_num, state, local_state
            )

            bad_attack = [
                key for key, value in local_state.items()
                if torch.is_floating_point(value)
                and not torch.isfinite(value).all()
            ]

            if bad_attack:
                raise RuntimeError(
                    f"Client {client_id}: non-finite values produced "
                    f"after applying {attacker.attack_type}: {bad_attack}"
                )

            if bool(fit_config.get("smpc_enabled", False)):
                if encoder is None or mpc_port is None:
                    raise RuntimeError("SPDZ2k client runtime was not initialized")
                credentials_dir = os.environ.get("FL_MPSPDZ_CLIENT_CREDENTIALS_DIR")
                if not credentials_dir:
                    raise RuntimeError(
                        "FL_MPSPDZ_CLIENT_CREDENTIALS_DIR must be provisioned in the client runtime"
                    )
                submit_client_update(
                    local_state,
                    num_examples=len(dataset),
                    client_id=client_id,
                    hosts=json.loads(fit_config["mp_spdz_client_hosts_json"]),
                    port_base=int(fit_config["mp_spdz_client_port_base"]),
                    credentials_dir=credentials_dir,
                    mp_spdz_home=os.environ["FL_MPSPDZ_HOME"],
                    encoder=encoder,
                    max_clients=num_clients,
                )

                return [], len(dataset), {
                    "client_id": client_id,
                    "mp_spdz_input_submitted": 1,
                }

            return (
                [
                    local_state[key].detach().cpu().numpy()
                    for key in state_keys
                ],
                len(dataset),
                {"client_id": client_id},
            )

        def evaluate(self, parameters, client_config):
            return 0.0, 0, {"flower_client_id": self.flower_cid}

    class ResearchStrategy(Strategy):
        """Flower strategy using MTD and active SPDZ2k aggregation."""
        def __init__(self):
            self.last_round_config = {}
            self.proxy_id_by_client = None
            self.last_selected, self.last_completed, self.last_malicious = [], [], []
            self.last_aggregation_seconds, self.last_mpc_input_bytes = 0.0, 0
            self.last_round_id = ""
            self.last_robust_report = {}
            self.robust_detector = (
                RobustUpdateDetector(
                    max_malicious=int(robust_config.get("max_malicious", 1)),
                    residual_z_threshold=float(robust_config.get("residual_z_threshold", 3.5)),
                    min_cosine_similarity=float(robust_config.get("min_cosine_similarity", 0.0)),
                    max_norm_ratio=float(robust_config.get("max_norm_ratio", 5.0)),
                    min_survivors=int(robust_config.get("min_survivors", 2)),
                    history_decay=float(robust_config.get("history_decay", 0.8)),
                    min_history_rounds=int(robust_config.get("min_history_rounds", 2)),
                    history_cosine_threshold=float(
                        robust_config.get("history_cosine_threshold", -0.25)
                    ),
                )
                if robust_enabled else None
            )

        def initialize_parameters(self, client_manager):
            return initial_parameters

        def configure_fit(self, server_round, parameters, client_manager):
            available = client_manager.all()

            # Flower generates opaque proxy IDs. Assign stable logical IDs
            # 0..num_clients-1 to the sorted proxy IDs once per simulation.
            if self.proxy_id_by_client is None:
                proxy_ids = sorted(available.keys())
                if len(proxy_ids) != num_clients:
                    raise RuntimeError(
                        f"Expected {num_clients} registered Flower clients, "
                        f"but found {len(proxy_ids)}: {proxy_ids}"
                    )
                self.proxy_id_by_client = {
                    logical_id: proxy_id
                    for logical_id, proxy_id in enumerate(proxy_ids)
                }
                print(
                    "[DEBUG] Flower proxy mapping (logical ID -> Flower ID): "
                    f"{self.proxy_id_by_client}",
                    flush=True,
                )

            self.last_round_config = mtd.generate_round_config(
                server_round,
                num_clients,
                float(fl_config.get("fraction_train", 1.0)),
            )
            self.last_selected = list(
                self.last_round_config["selected_clients"]
            )
            self.last_round_id = (
                f"{experiment_prefix}-r{server_round}-{uuid.uuid4().hex}"
            )

            print(
                f"[DEBUG] MTD selected logical clients: {self.last_selected}",
                flush=True,
            )

            missing_clients = [
                cid
                for cid in self.last_selected
                if self.proxy_id_by_client.get(int(cid)) not in available
            ]
            if use_smpc and missing_clients:
                raise RuntimeError(
                    "SPDZ2k round aborted before startup because selected clients "
                    f"are unavailable: {missing_clients}"
                )

            instructions = []
            for cid in self.last_selected:
                proxy_id = self.proxy_id_by_client.get(int(cid))
                proxy = available.get(proxy_id) if proxy_id is not None else None
                if proxy is None:
                    if use_smpc:
                        raise RuntimeError(f"selected SPDZ2k client {cid} is unavailable")
                    continue

                client_config = {
                    "server_round": int(server_round),
                    "client_id": int(cid),
                    "smpc_enabled": bool(use_smpc),
                }

                if use_smpc:
                    client_config.update({
                        "mp_spdz_client_hosts_json": json.dumps(
                            party_hosts, separators=(",", ":")
                        ),
                        "mp_spdz_client_port_base": int(mpc_port),
                    })

                instructions.append((proxy, FitIns(parameters, client_config)))

            if use_smpc:
                if len(self.last_selected) < min_clients:
                    raise RuntimeError(
                        f"SPDZ2k requires at least {min_clients} selected clients"
                    )
                start_round(
                    party_config,
                    self.last_round_id,
                    self.last_selected,
                    mpc_input_count,
                    [len(client_datasets[int(cid)]) for cid in self.last_selected],
                    num_clients,
                    mpc_port,
                )

            return instructions

        def aggregate_fit(self, server_round, results, failures):
            started = time.perf_counter()
            try:
                if not results:
                    self.last_completed = []
                    if use_smpc:
                        raise RuntimeError("SPDZ2k round aborted: no clients completed")
                    return None, {}

                client_ids = _resolve_authenticated_client_ids(
                    results, self.proxy_id_by_client, self.last_selected
                )
                reported_counts = [int(fit_res.num_examples) for _, fit_res in results]
                counts = [len(client_datasets[cid]) for cid in client_ids]
                count_mismatches = [
                    (cid, reported, expected)
                    for cid, reported, expected in zip(client_ids, reported_counts, counts)
                    if reported != expected
                ]
                self.last_completed = client_ids
                self.last_malicious = [
                    cid for cid in client_ids if attacker.is_malicious(cid, server_round)
                ]
                self.last_mpc_input_bytes = 0

                if use_smpc:
                    if encoder is None or mpc_port is None:
                        raise RuntimeError("SPDZ2k server runtime was not initialized")
                    if failures:
                        raise RuntimeError(
                            "SPDZ2k round aborted because one or more Flower clients failed"
                        )
                    if set(client_ids) != set(self.last_selected):
                        raise RuntimeError(
                            "SPDZ2k round aborted because a selected client did not complete"
                        )
                    if count_mismatches:
                        raise RuntimeError(
                            "Client-reported example counts do not match server-side partitions: "
                            f"{count_mismatches}"
                        )
                    if len(client_ids) < min_clients:
                        raise RuntimeError(
                            f"Only {len(client_ids)} clients completed; SPDZ2k requires "
                            f"{min_clients} for this experiment."
                        )
                    padded_input_count = (
                        (mpc_input_count + SPDZ2K_IO_CHUNK_SIZE - 1)
                        // SPDZ2K_IO_CHUNK_SIZE
                        * SPDZ2K_IO_CHUNK_SIZE
                    )
                    self.last_mpc_input_bytes = (
                        padded_input_count * 8 * len(client_ids) * len(party_config)
                    )
                    for _, fit_res in results:
                        metrics = getattr(fit_res, "metrics", {})
                        if not isinstance(metrics, Mapping):
                            raise RuntimeError("Flower returned invalid client metrics")
                        if metrics.get("mp_spdz_input_submitted") != 1:
                            raise RuntimeError(
                                "Flower client did not confirm its SPDZ2k input submission"
                            )
                        if parameters_to_ndarrays(fit_res.parameters):
                            raise RuntimeError(
                                "SPDZ2k mode received plaintext parameters; refusing fallback"
                            )

                    check_round_running(party_config, self.last_round_id)
                    credentials_dir = os.environ.get(
                        "FL_MPSPDZ_CLIENT_CREDENTIALS_DIR"
                    )
                    if not credentials_dir:
                        raise RuntimeError(
                            "FL_MPSPDZ_CLIENT_CREDENTIALS_DIR must be provisioned "
                            "for the aggregate-output client"
                        )
                    aggregated = receive_weighted_average(
                        global_model.state_dict(),
                        hosts=party_hosts,
                        port_base=mpc_port,
                        credentials_dir=credentials_dir,
                        mp_spdz_home=os.environ["FL_MPSPDZ_HOME"],
                        output_client_id=num_clients,
                        encoder=encoder,
                        expected_total_examples=sum(counts),
                    )
                    finish_round(party_config, self.last_round_id)
                    global_model.load_state_dict(aggregated)
                else:
                    if count_mismatches:
                        raise RuntimeError(
                            "Client-reported example counts do not match server-side partitions: "
                            f"{count_mismatches}"
                        )
                    client_states = []
                    for _, fit_res in results:
                        arrays = parameters_to_ndarrays(fit_res.parameters)
                        client_states.append({
                            key: torch.from_numpy(array.copy())
                            for key, array in zip(state_keys, arrays)
                        })
                    if robust_enabled:
                        aggregated, self.last_robust_report = self.robust_detector.aggregate(
                            client_states,
                            counts,
                            global_model.state_dict(),
                            client_ids=client_ids,
                        )
                    else:
                        self.last_robust_report = {}
                        aggregated = weighted_fedavg(
                            client_states, counts, global_model.state_dict()
                        )
                    global_model.load_state_dict(aggregated)

                self.last_aggregation_seconds = time.perf_counter() - started
                return (
                    ndarrays_to_parameters([
                        tensor.detach().cpu().numpy()
                        for tensor in global_model.state_dict().values()
                    ]),
                    {
                        "selected_clients": int(len(client_ids)),
                        "malicious_clients": int(len(self.last_malicious)),
                        "smpc_enabled": int(use_smpc),
                        "mp_spdz_input_bytes": int(self.last_mpc_input_bytes),
                        "aggregation_seconds": float(self.last_aggregation_seconds),
                        "mp_spdz_parties_used": len(party_config) if use_smpc else 0,
                    },
                )
            except Exception as error:
                if use_smpc:
                    try:
                        abort_round(party_config, self.last_round_id)
                    except Exception as abort_error:
                        error.add_note(f"SPDZ2k abort cleanup also failed: {abort_error}")
                raise

        def configure_evaluate(self, server_round, parameters, client_manager):
            return []

        def aggregate_evaluate(self, server_round, results, failures):
            return None, {}

        def evaluate(self, server_round, parameters):
            arrays = parameters_to_ndarrays(parameters)
            model = CIFAR10CNN()
            model.load_state_dict({
                key: torch.from_numpy(array.copy()) for key, array in zip(state_keys, arrays)
            })
            loss, accuracy = evaluate_model(model, testloader, device=device)
            logger.log_round({
                "round": int(server_round),
                "global_loss": float(loss),
                "global_accuracy": float(accuracy),
                "selected_clients": int(len(self.last_selected)),
                "completed_clients": int(len(self.last_completed)),
                "malicious_selected": int(len(self.last_malicious)),
                "smpc_enabled": int(use_smpc),
                "mtd_secret_seeded": int(self.last_round_config.get("secret_seeded", False)),
                "mp_spdz_parties_used": len(party_config) if use_smpc else 0,
                "mp_spdz_input_bytes": int(self.last_mpc_input_bytes),
                "aggregation_seconds": float(self.last_aggregation_seconds),
                "client_failures_or_omissions": int(
                    max(0, len(self.last_selected) - len(self.last_completed))
                ),
                "robust_aggregation_enabled": int(robust_enabled),
                "robust_aggregation_rule": self.last_robust_report.get(
                    "aggregation_rule", "fedavg"
                ),
                "detected_client_count": int(
                    self.last_robust_report.get("detected_client_count", 0)
                ),
                "detected_client_ids": json.dumps(
                    self.last_robust_report.get("detected_client_ids", [])
                ),
                "accepted_client_ids": json.dumps(
                    self.last_robust_report.get("accepted_client_ids", self.last_completed)
                ),
                "robust_fallback_used": int(
                    self.last_robust_report.get("fallback_used", False)
                ),
                "flagged_client_count": int(
                    self.last_robust_report.get("flagged_client_count", 0)
                ),
                "history_updated_client_ids": json.dumps(
                    self.last_robust_report.get("history_updated_client_ids", [])
                ),
                "detection_true_positives": int(
                    len(set(self.last_robust_report.get("detected_client_ids", []))
                        & set(self.last_malicious))
                ),
                "detection_false_positives": int(
                    len(set(self.last_robust_report.get("detected_client_ids", []))
                        - set(self.last_malicious))
                ),
                "detection_false_negatives": int(
                    len(set(self.last_malicious)
                        - set(self.last_robust_report.get("detected_client_ids", [])))
                ),
                "detection_precision": (
                    len(set(self.last_robust_report.get("detected_client_ids", []))
                        & set(self.last_malicious))
                    / max(1, len(self.last_robust_report.get("detected_client_ids", [])))
                ) if robust_enabled else None,
                "detection_recall": (
                    len(set(self.last_robust_report.get("detected_client_ids", []))
                        & set(self.last_malicious))
                    / max(1, len(self.last_malicious))
                ) if robust_enabled else None,
                "robust_client_scores_json": json.dumps(
                    self.last_robust_report.get("client_scores", []),
                    separators=(",", ":"),
                ),
            })
            return float(loss), {"accuracy": float(accuracy)}

        def summary(self):
            return None

    def client_fn(cid: str):
        return ResearchNumPyClient(cid).to_client()

    # Party control secrets stay on the coordinator. Client TLS credentials are
    # provisioned to each real client runtime; local simulation shares its
    # credential directory and is not an OS-level isolation boundary.
    server_only_names = (
        "FL_MPSPDZ_PARTIES_JSON",
        "FL_MPSPDZ_CONTROL_TOKEN",
        "FL_SMPC_AGGREGATORS_JSON",
        "FL_MTD_SECRET",
        "FL_SMPC_CONTROL_TOKEN",
        "FL_SMPC_CLIENT_KEYS_JSON",
        "FL_SMPC_CLIENT_TOKENS_JSON",
    )
    server_only_env = {
        name: os.environ.pop(name)
        for name in server_only_names
        if name in os.environ
    }
    try:
        start_simulation(
            client_fn=client_fn,
            num_clients=num_clients,
            config=ServerConfig(num_rounds=rounds),
            strategy=ResearchStrategy(),
            client_resources={
                "num_cpus": float(config.get("flower", {}).get("client_cpus", 1)),
                "num_gpus": float(config.get("flower", {}).get("client_gpus", 0)),
            },
            ray_init_args={"include_dashboard": False, "ignore_reinit_error": True},
        )
    finally:
        os.environ.update(server_only_env)
    evaluation, name = config.get("evaluation", {}), experiment.get("name", "fl_security_experiment")
    if evaluation.get("save_csv", True):
        logger.save_to_csv(f"{slug}_results.csv")
    if evaluation.get("save_plots", True):
        logger.plot_metrics(f"{slug}_accuracy.png")
    print(f"Flower experiment '{name}' completed.")
