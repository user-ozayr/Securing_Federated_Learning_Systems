"""Flower simulation with malicious-secure MP-SPDZ SPDZ2k aggregation.

Aggregation paths (selected by configuration):

* plaintext sample-weighted FedAvg (``smpc.enabled: false``);
* plaintext robust detector (``defences.robust_aggregation``) – reference only;
* plaintext execution of the norm defence algorithm
  (``defences.norm_defence_reference``) – reference only, no cryptography;
* SPDZ2k sum-only weighted aggregation (``smpc.enabled: true``);
* SPDZ2k robust aggregation with in-MPC clipping/screening
  (``smpc.enabled: true`` and ``smpc.defence.enabled: true``).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from collections.abc import Mapping
from numbers import Integral
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from fl_security.attacks.byzantine import ByzantineAttacker
from fl_security.evaluation.metrics import ExperimentLogger
from fl_security.federated.aggregation import (
    weighted_fedavg,
)
from fl_security.federated.dataset import load_cifar10_data, load_dataset, partition_data
from fl_security.federated.model import build_model, count_parameters
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
    receive_robust_result,
    receive_weighted_average,
    start_round,
    submit_client_delta,
    submit_client_update,
)
from fl_security.smpc.robust import (
    SecureDefenceConfig,
    apply_delta,
    decode_robust_output,
    direction_key,
    encode_delta,
    flatten_delta,
    robust_reference,
)

ROBUST_PROGRAM = "robust_aggregate"


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


def _defence_config(raw, label: str) -> SecureDefenceConfig | None:
    if not isinstance(raw, Mapping) or not raw.get("enabled", False):
        return None
    try:
        return SecureDefenceConfig.from_mapping(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label} configuration: {exc}") from exc


def _detection_counts(flags: dict[int, int], malicious: set[int]) -> dict[str, int]:
    flagged = {cid for cid, value in flags.items() if value}
    return {
        "tp": len(flagged & malicious),
        "fp": len(flagged - malicious),
        "fn": len((set(flags) & malicious) - flagged),
        "honest": len(set(flags) - malicious),
    }


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
    dataset_name = fl_config.get("dataset", "cifar10")
    model_name = fl_config.get(
        "model", "cifar10_cnn" if dataset_name == "cifar10" else "compact_cnn"
    )
    if dataset_name == "cifar10":
        trainset, testset = load_cifar10_data()
    else:
        trainset, testset = load_dataset(dataset_name, fl_config.get("data_root"))
    partitioning = fl_config.get("partitioning", "iid")
    if partitioning == "dirichlet":
        client_datasets = partition_data(
            trainset, num_clients, partitioning, seed,
            alpha=float(fl_config.get("dirichlet_alpha", 0.5)),
        )
    else:
        client_datasets = partition_data(trainset, num_clients, partitioning, seed)
    testloader = DataLoader(testset, batch_size=int(fl_config.get("eval_batch_size", 64)), shuffle=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    attacker, mtd = ByzantineAttacker(config, num_clients), MTDController(config)
    fraction = float(fl_config.get("fraction_train", 1.0))

    attack_config = config.get("attacks", {}) or {}
    adversary_model = attack_config.get("adversary_model")
    if attacker.enabled and adversary_model:
        from fl_security.mtd.exposure import (
            just_in_time_assignment,
            predicted_schedule,
            predictive_set,
        )

        predicted = predicted_schedule(config, num_clients, rounds, fraction)
        if adversary_model == "predictive":
            attacker.set_malicious_clients(
                predictive_set(predicted, attacker.malicious_count, num_clients, seed)
            )
        elif adversary_model == "just_in_time":
            attacker.set_round_assignment(
                just_in_time_assignment(predicted, attacker.malicious_count, num_clients, seed)
            )
        else:
            raise ValueError("attacks.adversary_model must be 'predictive' or 'just_in_time'")

    def make_model():
        return build_model(model_name, dataset_name)

    smpc_config = config.get("smpc", {})
    use_smpc = bool(smpc_config.get("enabled", False))
    min_clients = int(smpc_config.get("min_clients_per_round", 2))
    encoder, party_config, party_hosts, mpc_port = None, [], [], None
    mpc_input_count = 0
    defences = config.get("defences", {}) or {}
    robust_config = defences.get("robust_aggregation", {})
    robust_enabled = bool(robust_config.get("enabled", False))
    secure_defence = _defence_config(smpc_config.get("defence"), "smpc.defence")
    reference_defence = _defence_config(
        defences.get("norm_defence_reference"), "defences.norm_defence_reference"
    )
    if use_smpc and robust_enabled:
        raise ValueError(
            "Individual-update robust screening is not available with the current "
            "sum-only SMPC backend. Do not enable it until robust scoring and "
            "selection are implemented inside MPC."
        )
    if secure_defence is not None and not use_smpc:
        raise ValueError("smpc.defence requires smpc.enabled=true")
    if reference_defence is not None and (use_smpc or robust_enabled):
        raise ValueError("defences.norm_defence_reference is a plaintext-only comparison")
    if robust_enabled and num_clients < int(robust_config.get("min_survivors", 2)):
        raise ValueError("robust aggregation requires at least min_survivors clients")
    norm_defence = secure_defence or reference_defence

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
    global_model = make_model()
    initial_state = global_model.state_dict()
    parameter_count = count_parameters(global_model)

    # Direction screen key material. "secret": FL_MTD_SECRET if provisioned,
    # otherwise a fresh per-run key that is never stored, so clients cannot
    # predict the checked coordinates. "public": derived from the experiment seed.
    direction_enabled = norm_defence is not None and norm_defence.direction_check
    direction_material, direction_key_source = None, None
    if direction_enabled:
        if norm_defence.direction_subset == "secret":
            env_secret = os.environ.get("FL_MTD_SECRET")
            if env_secret:
                direction_material = hashlib.sha256(
                    b"direction-screen\x00" + env_secret.encode("utf-8")).digest()
                direction_key_source = "FL_MTD_SECRET"
            else:
                direction_material = secrets.token_bytes(32)
                direction_key_source = "per-run random key (not stored)"
        elif norm_defence.direction_subset == "public":
            direction_material = hashlib.sha256(f"public-direction-{seed}".encode()).digest()
            direction_key_source = "public seed"
        else:
            direction_key_source = "all coordinates"

    def direction_indices_for(round_num: int) -> list[int] | None:
        if not direction_enabled:
            return None
        key = (None if direction_material is None
               else direction_key(direction_material, round_num))
        return norm_defence.direction_indices(parameter_count, key)

    def direction_spec_for(round_num: int) -> dict | None:
        """What the parties receive for the round (never sent to clients)."""
        indices = direction_indices_for(round_num)
        if indices is None:
            return None
        return {"min_agree": norm_defence.min_agreement_count(len(indices)), "indices": indices}
    if use_smpc:
        mpc_input_count = sum(
            tensor.numel()
            for tensor in initial_state.values()
            if torch.is_floating_point(tensor)
        ) + 1
    state_keys = list(initial_state)
    initial_arrays = [tensor.detach().cpu().numpy() for tensor in initial_state.values()]
    initial_parameters = ndarrays_to_parameters(initial_arrays)
    evaluation_config = config.get("evaluation", {})
    logger = ExperimentLogger(output_dir=evaluation_config.get("output_dir", "./results"))
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", str(experiment.get("name", "fl")))
    experiment_prefix = f"{slug}-{seed}"
    instrumentation_dir = None
    if evaluation_config.get("instrumentation", False):
        # Evaluation-only side channel: clients record their submitted update for
        # offline influence analysis. It is not visible to the coordinator protocol.
        instrumentation_dir = (Path(logger.output_dir) / f"{slug}_instrumentation").resolve()
        instrumentation_dir.mkdir(parents=True, exist_ok=True)
        np.save(
            instrumentation_dir / "r0000_global.npy",
            torch.cat([
                t.detach().cpu().to(torch.float64).reshape(-1)
                for t in initial_state.values() if torch.is_floating_point(t)
            ]).numpy(),
        )
    asr_trigger = attacker.trigger
    if asr_trigger is None and evaluation_config.get("measure_backdoor_asr", False):
        from fl_security.attacks.backdoor import BackdoorTrigger

        backdoor_cfg = dict(attack_config.get("backdoor", {}) or {})
        asr_trigger = BackdoorTrigger(
            dataset=dataset_name,
            target_label=int(backdoor_cfg.get("target_label", 0)),
            size=int(backdoor_cfg.get("trigger_size", 4)),
        )

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
            model = make_model()
            model.load_state_dict(state)
            torch.manual_seed(seed + round_num * 100_000 + client_id)

            loader = DataLoader(
                dataset,
                batch_size=int(fl_config.get("batch_size", 32)),
                shuffle=True,
            )

            poisoning = attacker.data_poisoning(client_id, round_num)
            label_transform = None
            batch_transform = None
            if poisoning == "label_flip":
                def label_transform(labels):
                    values = attacker.perturb_labels(
                        client_id, round_num, labels, num_classes=10
                    )
                    return torch.as_tensor(
                        values, dtype=torch.long, device=labels.device
                    )
            elif poisoning == "backdoor":
                generator = torch.Generator()
                generator.manual_seed(seed + round_num * 1_000 + client_id)

                def batch_transform(images, labels):
                    return attacker.poison_batch(
                        client_id, round_num, images, labels, generator
                    )

            local_state = train_local(
                model,
                loader,
                epochs=int(fl_config.get("local_epochs", 1)),
                lr=float(fl_config.get("learning_rate", 0.01)),
                device=device,
                label_transform=label_transform,
                batch_transform=batch_transform,
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
            clean_state = None
            if attacker.needs_clean_update(client_id, round_num):
                # the evasive attacker also trains honestly, from the same model
                clean_model = make_model()
                clean_model.load_state_dict(state)
                torch.manual_seed(seed + round_num * 100_000 + client_id + 50_000)
                clean_state = train_local(
                    clean_model,
                    DataLoader(dataset, batch_size=int(fl_config.get("batch_size", 32)),
                               shuffle=True),
                    epochs=int(fl_config.get("local_epochs", 1)),
                    lr=float(fl_config.get("learning_rate", 0.01)),
                    device=device,
                )
            known = fit_config.get("direction_indices_json")
            estimate = fit_config.get("defence_threshold_estimate")
            local_state = attacker.perturb_update(
                client_id, round_num, state, local_state,
                threshold_estimate=None if estimate is None else float(estimate),
                clean_state_dict=clean_state,
                known_indices=None if known is None else json.loads(known),
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

            if instrumentation_dir is not None:
                delta = flatten_delta(local_state, state).numpy()
                np.savez(
                    instrumentation_dir / f"r{round_num:04d}_c{client_id:04d}.npz",
                    delta=delta,
                    malicious=np.array(attacker.is_malicious(client_id, round_num)),
                    num_examples=np.array(len(dataset)),
                )

            if bool(fit_config.get("smpc_enabled", False)):
                if encoder is None or mpc_port is None:
                    raise RuntimeError("SPDZ2k client runtime was not initialized")
                credentials_dir = os.environ.get("FL_MPSPDZ_CLIENT_CREDENTIALS_DIR")
                if not credentials_dir:
                    raise RuntimeError(
                        "FL_MPSPDZ_CLIENT_CREDENTIALS_DIR must be provisioned in the client runtime"
                    )
                submit_started = time.perf_counter()
                if fit_config.get("mp_spdz_program") == ROBUST_PROGRAM:
                    submitted_bytes = submit_client_delta(
                        local_state,
                        state,
                        num_examples=len(dataset),
                        client_id=client_id,
                        hosts=json.loads(fit_config["mp_spdz_client_hosts_json"]),
                        port_base=int(fit_config["mp_spdz_client_port_base"]),
                        credentials_dir=credentials_dir,
                        mp_spdz_home=os.environ["FL_MPSPDZ_HOME"],
                        fractional_bits=int(fit_config["robust_fractional_bits"]),
                        chunk_size=int(fit_config["robust_chunk_size"]),
                    )
                else:
                    submitted_bytes = submit_client_update(
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
                    "mp_spdz_submit_seconds": float(time.perf_counter() - submit_started),
                    "mp_spdz_client_bytes": int(submitted_bytes or 0),
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
            self.last_defence = {}
            self.last_timing = {}
            self.last_party_statistics = []
            self.round_started = 0.0
            self.threshold_estimate = (
                norm_defence.static_norm
                if norm_defence is not None and norm_defence.threshold == "static"
                else (norm_defence.max_norm if norm_defence is not None else None)
            )
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
            self.secure_weights: dict[int, int] = {}

        def initialize_parameters(self, client_manager):
            return initial_parameters

        def configure_fit(self, server_round, parameters, client_manager):
            self.round_started = time.perf_counter()
            self.last_timing = {}
            self.last_party_statistics = []
            self.last_defence = {}
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
                fraction,
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
                if self.threshold_estimate is not None and attacker.attack_type in (
                        "adaptive_backdoor", "evasive_backdoor"):
                    # Thresholds are public (static) or revealed every round
                    # (adaptive); the adaptive attacker is assumed to know them.
                    client_config["defence_threshold_estimate"] = float(self.threshold_estimate)
                if (attacker.attack_type == "evasive_backdoor" and direction_enabled
                        and norm_defence.direction_subset != "secret"):
                    # a public (or full) subset is known to every client
                    client_config["direction_indices_json"] = json.dumps(
                        direction_indices_for(int(server_round)))

                if use_smpc:
                    client_config.update({
                        "mp_spdz_client_hosts_json": json.dumps(
                            party_hosts, separators=(",", ":")
                        ),
                        "mp_spdz_client_port_base": int(mpc_port),
                    })
                    if secure_defence is not None:
                        client_config.update({
                            "mp_spdz_program": ROBUST_PROGRAM,
                            "robust_fractional_bits": int(secure_defence.fractional_bits),
                            "robust_chunk_size": int(secure_defence.chunk_size),
                        })

                instructions.append((proxy, FitIns(parameters, client_config)))

            if use_smpc:
                if len(self.last_selected) < min_clients:
                    raise RuntimeError(
                        f"SPDZ2k requires at least {min_clients} selected clients"
                    )
                counts = [len(client_datasets[int(cid)]) for cid in self.last_selected]
                started = time.perf_counter()
                if secure_defence is not None:
                    weights = secure_defence.quantized_weights(counts)
                    self.secure_weights = {
                        int(cid): int(weight) for cid, weight in zip(self.last_selected, weights)
                    }
                    start_round(
                        party_config,
                        self.last_round_id,
                        self.last_selected,
                        mpc_input_count,
                        counts,
                        num_clients,
                        mpc_port,
                        program=ROBUST_PROGRAM,
                        weights=weights,
                        robust_spec=secure_defence.round_spec(weights),
                        chunk_size=secure_defence.chunk_size,
                        direction=direction_spec_for(int(server_round)),
                    )
                else:
                    start_round(
                        party_config,
                        self.last_round_id,
                        self.last_selected,
                        mpc_input_count,
                        counts,
                        num_clients,
                        mpc_port,
                    )
                self.last_timing["mpc_start_seconds"] = time.perf_counter() - started

            return instructions

        def _apply_norm_defence(self, config_obj, client_ids, client_states, counts,
                                server_round=0):
            """Plaintext execution of the norm-defence algorithm (reference only)."""
            order = sorted(range(len(client_ids)), key=lambda i: client_ids[i])
            sorted_ids = [client_ids[i] for i in order]
            weights = config_obj.quantized_weights([counts[i] for i in order])
            spec = config_obj.round_spec(weights)
            base = global_model.state_dict()
            inputs = [
                encode_delta(client_states[i], base, config_obj.fractional_bits) for i in order
            ]
            indices = direction_indices_for(int(server_round))
            result = robust_reference(
                inputs, weights, spec, direction_indices=indices,
                min_agree=config_obj.min_agreement_count(len(indices)) if indices else 0)
            return sorted_ids, weights, decode_robust_output(result, weights, config_obj)

        def _record_norm_defence(self, sorted_ids, weights, decoded, config_obj):
            result = decoded.result
            malicious = set(self.last_malicious)
            accepted = {cid: int(a) for cid, a in zip(sorted_ids, result.accepted)}
            clipped = {cid: int(c) for cid, c in zip(sorted_ids, result.clip_flags)}
            rejected = {cid: 1 - a for cid, a in accepted.items()}
            flagged = {cid: max(rejected[cid], clipped[cid]) for cid in sorted_ids}
            detection = _detection_counts(flagged, malicious)
            rejection = _detection_counts(rejected, malicious)
            self.threshold_estimate = decoded.threshold_norm
            self.last_defence = {
                "defence_mode": config_obj.mode,
                "defence_threshold_rule": config_obj.threshold,
                "defence_threshold_norm": float(decoded.threshold_norm),
                "defence_accepted_client_ids": json.dumps(
                    [cid for cid in sorted_ids if accepted[cid]]),
                "defence_rejected_client_ids": json.dumps(
                    [cid for cid in sorted_ids if not accepted[cid]]),
                "defence_clipped_client_ids": json.dumps(
                    [cid for cid in sorted_ids if clipped[cid]]),
                "defence_clipped_count": int(result.clipped_count),
                "defence_accepted_weight": int(decoded.accepted_weight),
                "defence_aggregate_norm": float(decoded.aggregate_norm),
                "defence_output_check_passed": int(decoded.output_check_passed),
                "defence_update_applied": int(
                    decoded.output_check_passed and decoded.accepted_weight > 0),
                "flagged_true_positives": detection["tp"],
                "flagged_false_positives": detection["fp"],
                "flagged_false_negatives": detection["fn"],
                "honest_participants": detection["honest"],
                "rejected_true_positives": rejection["tp"],
                "rejected_false_positives": rejection["fp"],
                "weights_json": json.dumps(dict(zip(sorted_ids, weights))),
            }
            if result.direction_failed:
                direction = {cid: int(f) for cid, f in zip(sorted_ids, result.direction_failed)}
                counts_dir = _detection_counts(direction, malicious)
                self.last_defence.update({
                    "direction_rejected_client_ids": json.dumps(
                        [cid for cid in sorted_ids if direction[cid]]),
                    "direction_true_positives": counts_dir["tp"],
                    "direction_false_positives": counts_dir["fp"],
                    "direction_agreement_json": json.dumps(
                        dict(zip(sorted_ids, result.agreement))),
                    "direction_key_source": direction_key_source,
                })

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
                    chunk = (
                        secure_defence.chunk_size if secure_defence is not None
                        else SPDZ2K_IO_CHUNK_SIZE
                    )
                    padded_input_count = (mpc_input_count + chunk - 1) // chunk * chunk
                    self.last_mpc_input_bytes = (
                        padded_input_count * 8 * len(client_ids) * len(party_config)
                    )
                    submit_seconds = []
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
                        submit_seconds.append(float(metrics.get("mp_spdz_submit_seconds", 0.0)))
                    self.last_timing["mpc_client_submit_seconds_max"] = (
                        max(submit_seconds) if submit_seconds else 0.0
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
                    receive_started = time.perf_counter()
                    if secure_defence is not None:
                        result = receive_robust_result(
                            hosts=party_hosts,
                            port_base=mpc_port,
                            credentials_dir=credentials_dir,
                            mp_spdz_home=os.environ["FL_MPSPDZ_HOME"],
                            output_client_id=num_clients,
                            client_count=len(client_ids),
                            dimension=mpc_input_count - 1,
                            direction=direction_enabled,
                        )
                    else:
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
                    self.last_timing["mpc_receive_seconds"] = time.perf_counter() - receive_started
                    finish_started = time.perf_counter()
                    statistics = finish_round(party_config, self.last_round_id)
                    self.last_timing["mpc_finish_seconds"] = time.perf_counter() - finish_started
                    self.last_party_statistics = statistics if isinstance(statistics, list) else []
                    if secure_defence is not None:
                        sorted_ids = sorted(client_ids)
                        weights = [self.secure_weights[cid] for cid in sorted_ids]
                        decoded = decode_robust_output(result, weights, secure_defence)
                        self._record_norm_defence(sorted_ids, weights, decoded, secure_defence)
                        if decoded.output_check_passed and decoded.accepted_weight > 0:
                            global_model.load_state_dict(
                                apply_delta(global_model.state_dict(), decoded.delta)
                            )
                    else:
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
                        global_model.load_state_dict(aggregated)
                    elif reference_defence is not None:
                        self.last_robust_report = {}
                        sorted_ids, weights, decoded = self._apply_norm_defence(
                            reference_defence, client_ids, client_states, counts,
                            server_round=server_round,
                        )
                        self._record_norm_defence(sorted_ids, weights, decoded, reference_defence)
                        if decoded.output_check_passed and decoded.accepted_weight > 0:
                            global_model.load_state_dict(
                                apply_delta(global_model.state_dict(), decoded.delta)
                            )
                    else:
                        self.last_robust_report = {}
                        aggregated = weighted_fedavg(
                            client_states, counts, global_model.state_dict()
                        )
                        global_model.load_state_dict(aggregated)

                self.last_aggregation_seconds = time.perf_counter() - started
                if instrumentation_dir is not None:
                    np.save(
                        instrumentation_dir / f"r{server_round:04d}_global.npy",
                        torch.cat([
                            t.detach().cpu().to(torch.float64).reshape(-1)
                            for t in global_model.state_dict().values()
                            if torch.is_floating_point(t)
                        ]).numpy(),
                    )
                    spec = direction_spec_for(int(server_round))
                    if spec is not None:
                        # evaluation record only: lets the analysis recompute the
                        # round exactly; a deployment would not store the subset
                        np.save(
                            instrumentation_dir / f"r{server_round:04d}_direction.npy",
                            np.array([spec["min_agree"], *spec["indices"]], dtype=np.int64),
                        )
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
            model = make_model()
            model.load_state_dict({
                key: torch.from_numpy(array.copy()) for key, array in zip(state_keys, arrays)
            })
            loss, accuracy = evaluate_model(model, testloader, device=device)
            asr = None
            if asr_trigger is not None:
                from fl_security.attacks.backdoor import attack_success_rate

                asr = attack_success_rate(model, testloader, asr_trigger, device=device)
            stats = self.last_party_statistics
            protocol_seconds = [s.get("protocol_seconds") for s in stats if s.get("protocol_seconds") is not None]
            global_mb = [s.get("global_data_sent_mb") for s in stats if s.get("global_data_sent_mb") is not None]
            record = {
                "round": int(server_round),
                "global_loss": float(loss),
                "global_accuracy": float(accuracy),
                "backdoor_asr": None if asr is None else float(asr),
                "selected_clients": int(len(self.last_selected)),
                "completed_clients": int(len(self.last_completed)),
                "malicious_selected": int(len(self.last_malicious)),
                "selected_client_ids": json.dumps([int(c) for c in self.last_selected]),
                "malicious_client_ids": json.dumps([int(c) for c in self.last_malicious]),
                "smpc_enabled": int(use_smpc),
                "smpc_program": (
                    (ROBUST_PROGRAM if secure_defence is not None else "weighted_sum")
                    if use_smpc else "none"
                ),
                "mtd_enabled": int(bool(mtd.enabled)),
                "mtd_schedule": mtd.schedule or ("dynamic" if mtd.enabled else "static"),
                "mtd_secret_seeded": int(self.last_round_config.get("secret_seeded", False)),
                "model_parameters": int(parameter_count),
                "mp_spdz_parties_used": len(party_config) if use_smpc else 0,
                "mp_spdz_input_bytes": int(self.last_mpc_input_bytes),
                "aggregation_seconds": float(self.last_aggregation_seconds),
                "round_seconds": float(time.perf_counter() - self.round_started)
                if self.round_started else 0.0,
                "mpc_start_seconds": self.last_timing.get("mpc_start_seconds"),
                "mpc_client_submit_seconds_max": self.last_timing.get("mpc_client_submit_seconds_max"),
                "mpc_receive_seconds": self.last_timing.get("mpc_receive_seconds"),
                "mpc_finish_seconds": self.last_timing.get("mpc_finish_seconds"),
                "mpc_protocol_seconds_max": max(protocol_seconds) if protocol_seconds else None,
                "mpc_global_data_sent_mb": global_mb[0] if global_mb else None,
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
            }
            record.update(self.last_defence)
            logger.log_round(record)
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
    aborted: BaseException | None = None
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
    except Exception as exc:  # fail-closed abort: keep the rounds that did complete
        aborted = exc
    finally:
        os.environ.update(server_only_env)
    evaluation, name = config.get("evaluation", {}), experiment.get("name", "fl_security_experiment")
    if evaluation.get("save_csv", True) and logger.records:
        logger.save_to_csv(f"{slug}_results.csv")
    if aborted is not None:
        completed = max((int(r.get("round", 0)) for r in logger.records), default=0)
        cause = aborted.__cause__ or aborted
        (Path(logger.output_dir) / f"{slug}_abort.json").write_text(json.dumps({
            "error_type": type(aborted).__name__,
            "error": str(aborted)[:2000],
            "cause_type": type(cause).__name__,
            "cause": str(cause)[-2000:],
            "rounds_completed": completed,
            "rounds_configured": rounds,
        }, indent=2), encoding="utf-8")
        raise aborted
    if evaluation.get("save_plots", True):
        logger.plot_metrics(f"{slug}_accuracy.png")
    print(f"Flower experiment '{name}' completed.")
