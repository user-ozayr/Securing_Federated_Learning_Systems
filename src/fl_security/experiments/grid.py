"""Experiment definitions: configurations, attack scenarios and seeds.

Every run is fully described by a YAML configuration written next to its
results. Configurations share one base (dataset, model, partition, schedule
length) so that conditions differ only in the component under study.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

SEEDS = (101, 102, 103)
ROUNDS = 10

BASE = {
    "experiment": {"rounds": ROUNDS},
    "federated_learning": {
        "framework": "flower",
        "dataset": "fashion_mnist",
        "model": "compact_cnn",
        "num_clients": 12,
        "fraction_train": 0.34,  # 4 clients per round
        "local_epochs": 1,
        "batch_size": 32,
        "learning_rate": 0.05,
        "partitioning": "iid",
    },
    "mtd": {"schedule": "static"},
    "smpc": {"enabled": False},
    "attacks": {"enabled": False},
    "evaluation": {
        "save_csv": True,
        "save_plots": False,
        "instrumentation": True,
        "measure_backdoor_asr": True,
    },
}

SMPC = {
    "enabled": True,
    "backend": "mp_spdz_spdz2k",
    "fixed_point_scale": 1_000_000,
    "num_aggregation_parties": 3,
    "min_clients_per_round": 2,
}
# Sum-only aggregation uses a power-of-two scale. With S = 10^6 the decoded
# average rounds differently from float FedAvg at float32 ties, and SGD amplifies
# those one-ulp differences (diagnostics/sum_only_divergence); with S = 2^40 the
# same arithmetic reproduced FedAvg bit for bit. The encoder's ring guard
# (2^62 / num_clients) then admits |w| < ~70 for 5,000 samples and 12 clients;
# larger, diverged weights abort the round (fail-closed). The robust program has
# its own scale 2^f and is unaffected.
SMPC_SUM_ONLY = dict(SMPC, fixed_point_scale=1 << 40)

# Static public clipping bound: above the steady-state honest update norm
# (~3.1-3.9 in calibration) so that honest clients are rarely clipped after round 2.
CLIP_STATIC = {
    "enabled": True, "mode": "clip", "threshold": "static", "static_norm": 4.0,
    "min_norm": 0.25, "max_norm": 16.0, "max_valid_norm": 64.0,
    "fractional_bits": 14, "clip_bits": 8, "reveal_client_flags": True,
}
# Adaptive defence: clip to the cohort's lower-median norm, reject > 2x that.
DEFENCE_ADAPTIVE = {
    "enabled": True, "mode": "clip_screen", "threshold": "adaptive",
    "median_multiplier_squared": 1, "screen_multiplier_squared": 4,
    "static_norm": 4.0, "min_norm": 0.25, "max_norm": 16.0, "max_valid_norm": 64.0,
    "fractional_bits": 14, "clip_bits": 8, "reveal_client_flags": True,
}
# Screen-only: the output bound is rho * tau_max (= 32), which needs a larger
# margin than clipping; clipping is off, so g only scales contributions and
# clip_bits 6 satisfies 2^31 / (2^(g+f) * K) >= 2 * margin * rho * tau_max.
SCREEN_ADAPTIVE = dict(DEFENCE_ADAPTIVE, mode="screen", clip_bits=6)

CONFIGS = {
    # name: (description, overrides)
    "baseline": ("FedAvg, plaintext, static participation", {}),
    "mtd_only": ("FedAvg, plaintext, secret-derived MTD", {"mtd": {"schedule": "secret"}}),
    "smpc_only": ("SPDZ2k sum-only aggregation, static participation", {"smpc": SMPC_SUM_ONLY}),
    "smpc_mtd": ("SPDZ2k sum-only aggregation, secret-derived MTD",
                 {"smpc": SMPC_SUM_ONLY, "mtd": {"schedule": "secret"}}),
    "smpc_clip": ("SPDZ2k + secure L2 clipping (static public bound)",
                  {"smpc": dict(SMPC, defence=CLIP_STATIC)}),
    "smpc_defence_mtd": ("SPDZ2k + secure adaptive clip+screen + secret MTD (full framework)",
                         {"smpc": dict(SMPC, defence=DEFENCE_ADAPTIVE), "mtd": {"schedule": "secret"}}),
    "plaintext_robust": ("Plaintext robust detector (median/cosine/norm/temporal), static",
                         {"defences": {"robust_aggregation": {
                             "enabled": True, "max_malicious": 1, "residual_z_threshold": 3.5,
                             "min_cosine_similarity": 0.0, "max_norm_ratio": 2.0,
                             "min_survivors": 2, "history_decay": 0.8,
                             "min_history_rounds": 2, "history_cosine_threshold": -0.25}}}),
    "smpc_screen": ("SPDZ2k + secure adaptive norm screening only, static",
                    {"smpc": dict(SMPC, defence=SCREEN_ADAPTIVE)}),
    "smpc_defence": ("SPDZ2k + secure adaptive clip+screen, static participation",
                     {"smpc": dict(SMPC, defence=DEFENCE_ADAPTIVE)}),
    "reference_defence": ("Plaintext execution of the adaptive clip+screen algorithm (no MPC)",
                          {"defences": {"norm_defence_reference": DEFENCE_ADAPTIVE}}),
    "reference_clip": ("Plaintext execution of static clipping (no MPC)",
                       {"defences": {"norm_defence_reference": CLIP_STATIC}}),
}

BACKDOOR = {"target_label": 0, "trigger_size": 4, "poison_fraction": 0.5}
ATTACKS = {
    "none": {"enabled": False},
    "label_flip": {"enabled": True, "attack_type": "label_flip"},
    "sign_flip": {"enabled": True, "attack_type": "sign_flip", "strength": 4.0},
    "scaled_replacement": {"enabled": True, "attack_type": "scaled_replacement", "boost": 4.0},
    "random_noise": {"enabled": True, "attack_type": "random_noise", "strength": 0.2},
    "backdoor": {"enabled": True, "attack_type": "backdoor", "boost": 4.0, "backdoor": BACKDOOR},
    "adaptive_backdoor": {"enabled": True, "attack_type": "adaptive_backdoor",
                          "adaptive_norm_fraction": 0.95, "boost": 4.0, "backdoor": BACKDOOR},
}
ATTACK_DEFAULTS = {"num_malicious": 3, "placement": "stratified"}


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@dataclass
class RunSpec:
    run_id: str
    study: str
    condition: str
    attack: str
    seed: int
    config: dict
    priority: tuple
    tags: dict = field(default_factory=dict)

    @property
    def uses_mpc(self) -> bool:
        return bool(self.config.get("smpc", {}).get("enabled", False))

    @property
    def needs_secret(self) -> bool:
        return self.config.get("mtd", {}).get("schedule") == "secret"


def make_run(study: str, condition: str, attack: str, seed: int, priority: tuple,
             extra: dict | None = None, attack_extra: dict | None = None, suffix: str = "") -> RunSpec:
    description, overrides = CONFIGS[condition]
    config = deep_merge(BASE, overrides)
    attack_cfg = deep_merge(ATTACKS[attack], ATTACK_DEFAULTS if attack != "none" else {})
    if attack_extra:
        attack_cfg = deep_merge(attack_cfg, attack_extra)
    config["attacks"] = attack_cfg
    if extra:
        config = deep_merge(config, extra)
    run_id = f"{study}__{condition}__{attack}{suffix}__s{seed}"
    config["experiment"]["name"] = run_id
    config["experiment"]["seed"] = int(seed)
    return RunSpec(run_id, study, condition, attack + suffix, seed, config, priority,
                   {"description": description})


E1_ATTACKS = ("none", "label_flip", "sign_flip", "scaled_replacement", "random_noise", "backdoor")


def e1_core() -> list[RunSpec]:
    """Required six-configuration comparison under six attack scenarios.

    Ordered seed-major so that every completed seed is a complete paired set.
    """
    runs = []
    order = ["smpc_defence_mtd", "baseline", "smpc_clip", "mtd_only", "smpc_only", "smpc_mtd"]
    for seed_index, seed in enumerate(SEEDS):
        for index, condition in enumerate(order):
            for attack_index, attack in enumerate(E1_ATTACKS):
                runs.append(make_run("e1", condition, attack, seed,
                                     priority=(1, seed_index, 0, index, attack_index)))
    return runs


def e1_extended() -> list[RunSpec]:
    runs = []
    for seed_index, seed in enumerate(SEEDS):
        for index, condition in enumerate(["plaintext_robust", "smpc_defence", "smpc_screen"]):
            for attack_index, attack in enumerate(("none", "scaled_replacement", "backdoor", "sign_flip")):
                runs.append(make_run("e1x", condition, attack, seed,
                                     priority=(2, seed_index, 0, index, attack_index)))
    return runs


def e2_adaptive() -> list[RunSpec]:
    """Adaptive (constrain-and-scale) backdoor attacker against each defence."""
    runs = []
    for seed_index, seed in enumerate(SEEDS):
        for index, condition in enumerate(["smpc_defence_mtd", "smpc_clip", "baseline",
                                           "plaintext_robust"]):
            runs.append(make_run("e2", condition, "adaptive_backdoor", seed,
                                 priority=(1, seed_index, 2, index, 0)))
    return runs


def e3_mtd() -> list[RunSpec]:
    """Schedule predictability: static, deterministic and secret schedules vs.
    a predictive adversary that compromises the clients it expects to be selected."""
    runs = []
    schedules = {"static": "static", "deterministic": "deterministic", "secret": "secret"}
    for seed_index, seed in enumerate(SEEDS):
        for index, (label, schedule) in enumerate(schedules.items()):
            for adversary_index, adversary in enumerate(("predictive", "just_in_time")):
                extra = {"mtd": {"schedule": schedule}}
                attack_extra = {"adversary_model": adversary, "placement": "random",
                                "num_malicious": 2}
                runs.append(make_run(
                    "e3", "baseline", "backdoor", seed,
                    priority=(1, 0, 1, seed_index, index * 2 + adversary_index),
                    extra=extra, attack_extra=attack_extra, suffix=f"__{label}__{adversary}"))
    return runs


def e4_sweeps() -> list[RunSpec]:
    """Malicious proportion and attack strength sweeps (plaintext FedAvg and the
    plaintext execution of the same defence algorithm that runs in SPDZ2k),
    plus reference runs at the default setting for the SPDZ2k equivalence check."""
    runs = []
    for seed_index, seed in enumerate(SEEDS[:2]):
        runs.append(make_run("e4", "reference_defence", "backdoor", seed,
                             priority=(3, seed_index, 0, 0, 0), suffix="__default"))
        for condition_index, condition in enumerate(("baseline", "reference_defence")):
            for count in (1, 2, 4, 5):
                runs.append(make_run(
                    "e4", condition, "backdoor", seed, priority=(3, seed_index, 1, condition_index, count),
                    attack_extra={"num_malicious": count}, suffix=f"__m{count}"))
            for boost in (1.0, 2.0, 8.0, 16.0):
                runs.append(make_run(
                    "e4", condition, "backdoor", seed, priority=(3, seed_index, 2, condition_index, int(boost)),
                    attack_extra={"boost": boost}, suffix=f"__boost{int(boost)}"))
            for strength in (1.0, 2.0, 8.0):
                runs.append(make_run(
                    "e4", condition, "sign_flip", seed, priority=(3, seed_index, 3, condition_index, int(strength)),
                    attack_extra={"strength": strength}, suffix=f"__str{int(strength)}"))
    return runs


def e5_noniid() -> list[RunSpec]:
    runs = []
    extra = {"federated_learning": {"partitioning": "dirichlet", "dirichlet_alpha": 0.5}}
    # Sample weights enlarge sum(w); clip_bits 6 and 2-bit weights keep the
    # output-check margin 2^31 / (2^(g+f) * sum(w)) >= 2 * margin * max_norm.
    weighted = {"smpc": {"defence": {"weighting": "sample", "weight_bits": 2, "clip_bits": 6}}}
    for seed_index, seed in enumerate(SEEDS[:2]):
        for attack_index, attack in enumerate(("none", "backdoor")):
            runs.append(make_run("e5", "baseline", attack, seed, (4, seed_index, 0, 0, attack_index),
                                 extra=extra, suffix="__dir05"))
            runs.append(make_run("e5", "smpc_defence_mtd", attack, seed, (4, seed_index, 0, 1, attack_index),
                                 extra=deep_merge(extra, weighted), suffix="__dir05"))
    return runs


STUDIES = {
    "e1": e1_core,
    "e1x": e1_extended,
    "e2": e2_adaptive,
    "e3": e3_mtd,
    "e4": e4_sweeps,
    "e5": e5_noniid,
}


def all_runs(studies: list[str] | None = None) -> list[RunSpec]:
    selected = studies or list(STUDIES)
    runs = [run for name in selected for run in STUDIES[name]()]
    ids = [run.run_id for run in runs]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate run identifiers in the experiment grid")
    return sorted(runs, key=lambda run: (run.priority, run.run_id))
