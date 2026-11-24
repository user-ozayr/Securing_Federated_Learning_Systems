from pathlib import Path
import yaml

def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    validate_config(config)
    return config

def validate_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("configuration root must be a mapping")
    for section in ("experiment", "federated_learning"):
        if section not in config or not isinstance(config[section], dict):
            raise ValueError(f"missing or invalid {section!r} section")
    experiment, fl = config["experiment"], config["federated_learning"]
    rounds = experiment.get("rounds")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds <= 0:
        raise ValueError("experiment.rounds must be a positive integer")
    clients = fl.get("num_clients")
    if isinstance(clients, bool) or not isinstance(clients, int) or clients < 2:
        raise ValueError("federated_learning.num_clients must be an integer >= 2")
    fraction = fl.get("fraction_train", 1.0)
    if not isinstance(fraction, (int, float)) or not 0 < fraction <= 1:
        raise ValueError("federated_learning.fraction_train must be in (0, 1]")
    if fl.get("framework", "flower") != "flower":
        raise ValueError("federated_learning.framework must be 'flower'")

    mtd, smpc = config.get("mtd", {}), config.get("smpc", {})
    if not isinstance(mtd, dict) or not isinstance(smpc, dict):
        raise ValueError("mtd and smpc sections must be mappings")
    if smpc.get("enabled", False):
        if smpc.get("backend") != "mp_spdz_spdz2k":
            raise ValueError(
                "smpc.backend must be 'mp_spdz_spdz2k'; no other backend or fallback is supported"
            )
        parties = smpc.get("num_aggregation_parties")
        minimum = smpc.get("min_clients_per_round", 2)
        scale = smpc.get("fixed_point_scale", 1_000_000)
        for key, value in (
            ("num_aggregation_parties", parties),
            ("min_clients_per_round", minimum),
            ("fixed_point_scale", scale),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"smpc.{key} must be an integer")
        if parties < 2:
            raise ValueError("smpc.num_aggregation_parties must be >= 2")
        if minimum < 2:
            raise ValueError("smpc.min_clients_per_round must be >= 2")
        if scale <= 0:
            raise ValueError("smpc.fixed_point_scale must be positive")
        if "threshold" in smpc or smpc.get("dropout_recovery", False):
            raise ValueError(
                "SPDZ2k uses malicious security with abort and does not support dropout recovery"
            )
        selected_count = max(1, int(clients * fraction))
        if selected_count < minimum:
            raise ValueError("client fraction is too low for smpc.min_clients_per_round")

    compromised_fraction = float(config.get("attacks", {}).get("compromised_fraction", 0.0))
    if not 0 <= compromised_fraction <= 1:
        raise ValueError("attacks.compromised_fraction must be in [0, 1]")
