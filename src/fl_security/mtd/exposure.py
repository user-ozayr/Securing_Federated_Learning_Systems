"""Adversary models and exposure metrics for participation scheduling (MTD).

Threat model: an adversary can compromise a budget of ``b`` clients. It does
not know FL_MTD_SECRET. It may know the public configuration, including the
experiment seed (for example because experiments are published to be
reproducible). It predicts the schedule by running the public, secret-free
scheduler. Against static or deterministic schedules this prediction is exact;
against a secret-derived schedule it is independent of the real cohorts.

Two adversaries are modelled:

* ``predictive``: compromises, once, the ``b`` clients with the highest
  predicted participation count over the whole run;
* ``just_in_time``: compromises, in every round, ``b`` members of that round's
  predicted cohort (an upper bound for adversaries that can move between
  clients, e.g. by targeting whichever devices are about to be selected).
"""
from __future__ import annotations

import copy
import os
from collections import Counter
from contextlib import contextmanager

import numpy as np

from fl_security.mtd.controller import MTDController


@contextmanager
def _without_secret():
    saved = os.environ.pop("FL_MTD_SECRET", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["FL_MTD_SECRET"] = saved


def schedule(config: dict, num_clients: int, rounds: int, fraction: float) -> dict[int, list[int]]:
    """Actual cohorts produced by MTDController (uses FL_MTD_SECRET if configured)."""
    controller = MTDController(config)
    return {
        r: list(controller.generate_round_config(r, num_clients, fraction)["selected_clients"])
        for r in range(1, rounds + 1)
    }


def predicted_schedule(config: dict, num_clients: int, rounds: int, fraction: float) -> dict[int, list[int]]:
    """The adversary's prediction: the same scheduler without the secret."""
    public = copy.deepcopy(config)
    mtd = public.setdefault("mtd", {})
    if mtd.get("schedule") == "secret":
        mtd["schedule"] = "deterministic"
    with _without_secret():
        controller = MTDController(public)
        return {
            r: list(controller.generate_round_config(r, num_clients, fraction)["selected_clients"])
            for r in range(1, rounds + 1)
        }


def predictive_set(predicted: dict[int, list[int]], budget: int, num_clients: int, seed: int) -> set[int]:
    """The ``budget`` clients with the highest predicted participation."""
    counts = Counter(c for cohort in predicted.values() for c in cohort)
    rng = np.random.default_rng(seed + 31_337)
    tiebreak = rng.permutation(num_clients)
    ranked = sorted(range(num_clients), key=lambda c: (-counts.get(c, 0), int(tiebreak[c])))
    return set(int(c) for c in ranked[:budget])


def just_in_time_assignment(predicted: dict[int, list[int]], budget: int, num_clients: int,
                            seed: int) -> dict[int, set[int]]:
    rng = np.random.default_rng(seed + 31_338)
    assignment = {}
    for round_num, cohort in predicted.items():
        cohort = list(cohort)
        chosen = [int(c) for c in rng.permutation(cohort)[: min(budget, len(cohort))]]
        if len(chosen) < budget:
            rest = [c for c in range(num_clients) if c not in chosen]
            chosen += [int(c) for c in rng.permutation(rest)[: budget - len(chosen)]]
        assignment[int(round_num)] = set(chosen)
    return assignment


def exposure_metrics(actual: dict[int, list[int]], malicious_by_round: dict[int, set[int]],
                     predicted: dict[int, list[int]] | None = None) -> dict:
    rounds = sorted(actual)
    counts = np.array([len(set(actual[r]) & malicious_by_round[r]) for r in rounds], dtype=float)
    sizes = np.array([len(actual[r]) for r in rounds], dtype=float)
    shares = counts / np.maximum(sizes, 1)
    streak = longest = 0
    for value in counts:
        streak = streak + 1 if value > 0 else 0
        longest = max(longest, streak)
    compromised = [len(malicious_by_round[r]) for r in rounds]
    hit_rate = float(np.sum(counts) / max(1, np.sum(compromised)))
    result = {
        "rounds": len(rounds),
        "mean_malicious_per_round": float(counts.mean()),
        "mean_malicious_share": float(shares.mean()),
        "max_malicious_share": float(shares.max()),
        "rounds_with_any_malicious": float((counts > 0).mean()),
        "rounds_with_malicious_majority": float((shares > 0.5).mean()),
        "longest_malicious_streak": int(longest),
        "compromise_hit_rate": hit_rate,
    }
    if predicted is not None:
        overlap = [len(set(actual[r]) & set(predicted[r])) / max(1, len(actual[r])) for r in rounds]
        result["prediction_accuracy"] = float(np.mean(overlap))
    return result
