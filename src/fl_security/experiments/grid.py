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
        "fraction_train": 0.34,  # Each round includes 4 clients.
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
# Sum-only aggregation uses a power-of-two scale. At S = 10^6, float32 ties can
# make its decoded average round differently from float FedAvg. SGD then amplifies
# those one-ulp differences, as the divergence diagnostics show. With S = 2^40, the
# tested arithmetic reproduced FedAvg bit for bit. The encoder ring guard
# (2^62 / num_clients) admits |w| below about 70 for 5,000 samples and 12 clients.
# Larger diverged weights abort the round. The robust program uses its own 2^f
# scale, so this setting does not affect it.
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

# Moving-target direction screen (plaintext reference of the algorithm; M1 study).
DIRECTION = {"direction_check": True, "direction_fraction": 0.25, "direction_min_agreement": 0.5}
for _name, _subset, _extra in (
    ("reference_direction_all", "all", {}),
    ("reference_direction_public", "public", {}),
    ("reference_direction_secret", "secret", {}),
    ("reference_direction_secret_t52", "secret", {"direction_min_agreement": 0.52}),
):
    CONFIGS[_name] = (
        f"Adaptive clip+screen plus sign-agreement direction screen ({_subset} subset)",
        {"defences": {"norm_defence_reference": {
            **DEFENCE_ADAPTIVE, **DIRECTION, "direction_subset": _subset, **_extra}}})
# M2: the stricter agreement threshold for every subset type, and a 10 % subset
for _name, _subset, _fraction in (
    ("reference_direction_all_t52", "all", 0.25),
    ("reference_direction_public_t52", "public", 0.25),
    ("reference_direction_secret10_t52", "secret", 0.10),
):
    CONFIGS[_name] = (
        f"Direction screen ({_subset} subset, fraction {_fraction}), min agreement 0.52",
        {"defences": {"norm_defence_reference": {
            **DEFENCE_ADAPTIVE, **DIRECTION, "direction_subset": _subset,
            "direction_fraction": _fraction, "direction_min_agreement": 0.52}}})
CONFIGS["reference_direction_secret_mtd"] = (
    "Direction screen on a secret subset plus secret MTD cohorts",
    {"defences": {"norm_defence_reference": dict(DEFENCE_ADAPTIVE, **DIRECTION,
                                                 direction_subset="secret")},
     "mtd": {"schedule": "secret"}})
CONFIGS["reference_direction_secret_mtd_t52"] = (
    "Direction screen on a secret 25 % subset (min agreement 0.52) plus secret MTD cohorts",
    {"defences": {"norm_defence_reference": {**DEFENCE_ADAPTIVE, **DIRECTION,
                                             "direction_subset": "secret",
                                             "direction_min_agreement": 0.52}},
     "mtd": {"schedule": "secret"}})
CONFIGS["reference_defence_mtd"] = (
    "Adaptive clip+screen (plaintext reference) plus secret MTD cohorts",
    {"defences": {"norm_defence_reference": DEFENCE_ADAPTIVE}, "mtd": {"schedule": "secret"}})

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
    "evasive_backdoor": {"enabled": True, "attack_type": "evasive_backdoor",
                         "adaptive_norm_fraction": 0.95, "boost": 4.0, "backdoor": BACKDOOR,
                         "evasion_guess_fraction": 0.25},
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

    @property
    def uses_secret_subset(self) -> bool:
        """The direction screen checks a secret subset (keyed by FL_MTD_SECRET when set)."""
        defences = [self.config.get("defences", {}).get("norm_defence_reference") or {},
                    self.config.get("smpc", {}).get("defence") or {}]
        return any(d.get("direction_check") and d.get("direction_subset", "secret") == "secret"
                   for d in defences)


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
    """Run six configurations against each of the six attack scenarios.

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
    """Compare each defence against the constrain-and-scale backdoor attack."""
    runs = []
    for seed_index, seed in enumerate(SEEDS):
        for index, condition in enumerate(["smpc_defence_mtd", "smpc_clip", "baseline",
                                           "plaintext_robust"]):
            runs.append(make_run("e2", condition, "adaptive_backdoor", seed,
                                 priority=(1, seed_index, 2, index, 0)))
    return runs


def e3_mtd() -> list[RunSpec]:
    """Compare static, deterministic, and secret schedules against a predictive
    adversary that targets the clients it expects to be selected."""
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
    """Sweep malicious-client share and attack strength for plaintext FedAvg and
    the plaintext version of the SPDZ2k defence, then add default-setting runs
    for the SPDZ2k equivalence check."""
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


def m1_direction() -> list[RunSpec]:
    """Moving-target direction screen (plaintext reference, 2 seeds).

    Norm defence alone vs the direction screen on all coordinates, on a public
    and on a secret 25 % subset, and with secret MTD cohorts; attackers include
    an evasive backdoor that hides in the coordinates it believes are checked.
    """
    runs = []
    conditions = ("reference_defence", "reference_direction_all", "reference_direction_public",
                  "reference_direction_secret", "reference_direction_secret_t52",
                  "reference_defence_mtd", "reference_direction_secret_mtd")
    attacks = ("none", "label_flip", "backdoor", "adaptive_backdoor", "evasive_backdoor")
    for seed_index, seed in enumerate(SEEDS[:2]):
        for index, condition in enumerate(conditions):
            for attack_index, attack in enumerate(attacks):
                runs.append(make_run("m1", condition, attack, seed,
                                     priority=(5, seed_index, 0, index, attack_index)))
    return runs


def m2_direction_strict() -> list[RunSpec]:
    """Direction screen at min agreement 0.52: all coordinates, a public and a
    secret 25 % subset, and a secret 10 % subset (3 seeds). The evasive attacker
    tests whether keeping the subset secret is what makes the screen hold."""
    runs = []
    conditions = ("reference_direction_all_t52", "reference_direction_public_t52",
                  "reference_direction_secret_t52", "reference_direction_secret10_t52")
    attacks = ("none", "label_flip", "backdoor", "adaptive_backdoor", "evasive_backdoor")
    for seed_index, seed in enumerate(SEEDS):
        for index, condition in enumerate(conditions):
            for attack_index, attack in enumerate(attacks):
                runs.append(make_run("m2", condition, attack, seed,
                                     priority=(6, seed_index, 0, index, attack_index)))
    return runs


# M3: cohorts of K = 7 >= 2f + 1 (f = 3), so that every cohort has an honest
# majority whichever clients a secret schedule draws. int(12 * 0.59) = 7.
# clip_bits 7 keeps the SPDZ2k output margin 2^31 / (2^(g+f) * K) at 146 (K = 4,
# g = 8 gives 128), so the same parameters remain valid inside the MPC program.
M3_COHORT = {"federated_learning": {"fraction_train": 0.59},
             "defences": {"norm_defence_reference": {"clip_bits": 7}}}


def m3_cohort_bound(seeds: tuple = SEEDS, study: str = "m3", paired: bool = False,
                    block: int = 7) -> list[RunSpec]:
    """Static vs secret MTD cohorts of K = 7, norm defence with and without the
    secret direction screen. Attackers: 3 stratified adaptive / evasive backdoors,
    and a just-in-time adversary that corrupts 4 of the clients it predicts will
    be selected (exact for the static schedule, a guess for the secret one)."""
    runs = []
    conditions = ("reference_defence", "reference_defence_mtd",
                  "reference_direction_secret_t52", "reference_direction_secret_mtd_t52")
    attacks = (("none", None, ""), ("adaptive_backdoor", None, ""),
               ("evasive_backdoor", None, ""),
               ("adaptive_backdoor", {"adversary_model": "just_in_time", "placement": "random",
                                      "num_malicious": 4}, "__jit4"))
    for seed_index, seed in enumerate(seeds):
        for index, condition in enumerate(conditions):
            for attack_index, (attack, attack_extra, suffix) in enumerate(attacks):
                run = make_run(study, condition, attack, seed,
                               priority=(block, seed_index, 0, index, attack_index),
                               extra=M3_COHORT, attack_extra=attack_extra, suffix=suffix)
                run.tags["paired"] = paired
                runs.append(run)
    return runs


# F1: the final framework inside SPDZ2k at the M3 setting (K = 7, clip_bits 7):
# secure adaptive clip+screen, sign-agreement screen on a secret 25 % subset
# (min agreement 0.52) and secret MTD cohorts.
DEFENCE_DIRECTION_K7 = {**DEFENCE_ADAPTIVE, **DIRECTION, "direction_subset": "secret",
                        "direction_min_agreement": 0.52, "clip_bits": 7}
CONFIGS["smpc_direction_mtd"] = (
    "SPDZ2k + secure adaptive clip+screen + secret-subset direction screen + secret MTD",
    {"smpc": dict(SMPC, defence=DEFENCE_DIRECTION_K7), "mtd": {"schedule": "secret"},
     "federated_learning": {"fraction_train": 0.59}})
F1_ATTACKS = (("adaptive_backdoor", {"adversary_model": "just_in_time", "placement": "random",
                                     "num_malicious": 4}, "__jit4"),
              ("adaptive_backdoor", None, ""), ("evasive_backdoor", None, ""),
              ("none", None, ""), ("label_flip", None, ""))


def f1_framework(pilot: bool = False) -> list[RunSpec]:
    """Final framework in SPDZ2k; seed-major so each finished seed is a full set."""
    runs = []
    for seed_index, seed in enumerate(SEEDS[:1] if pilot else SEEDS):
        for attack_index, (attack, attack_extra, suffix) in enumerate(F1_ATTACKS[:1] if pilot else F1_ATTACKS):
            runs.append(make_run("f1", "smpc_direction_mtd", attack, seed,
                                 priority=(9, seed_index, 0, 0, attack_index),
                                 attack_extra=attack_extra, suffix=suffix))
    return runs


def p3_paired() -> list[RunSpec]:
    """M3 repeated with paired secrets and five seeds: within a seed, all four
    conditions see the same secret cohorts (MTD conditions) and the same secret
    direction subsets, so condition differences are not cohort-draw luck."""
    return m3_cohort_bound(seeds=SEEDS + (104, 105), study="p3", paired=True, block=10)


def m2b_norm_baseline() -> list[RunSpec]:
    """The norm defence alone at seed 103, which M1 (seeds 101, 102) lacks, so
    that M2 compares with a three-seed baseline."""
    attacks = ("none", "label_flip", "backdoor", "adaptive_backdoor", "evasive_backdoor")
    return [make_run("m2b", "reference_defence", attack, SEEDS[2], priority=(8, 0, 0, 0, index))
            for index, attack in enumerate(attacks)]


STUDIES = {
    "e1": e1_core,
    "e1x": e1_extended,
    "e2": e2_adaptive,
    "e3": e3_mtd,
    "e4": e4_sweeps,
    "e5": e5_noniid,
    "m1": m1_direction,
    "m2": m2_direction_strict,
    "m3": m3_cohort_bound,
    "p3": p3_paired,
    "m2b": m2b_norm_baseline,
    # The F1 pilot (f1_framework(pilot=True)) was run first and is the first F1
    # run; it is not a separate study, so the full grid has no duplicate ids.
    "f1": f1_framework,
}


def all_runs(studies: list[str] | None = None) -> list[RunSpec]:
    selected = studies or list(STUDIES)
    runs = [run for name in selected for run in STUDIES[name]()]
    ids = [run.run_id for run in runs]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate run identifiers in the experiment grid")
    return sorted(runs, key=lambda run: (run.priority, run.run_id))
