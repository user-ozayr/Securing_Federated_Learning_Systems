"""Monte-Carlo study of participation exposure under different MTD schedules.

For each trial (experiment seed; a fresh random FL_MTD_SECRET for the secret
schedule) and each adversary model the study computes the exposure metrics of
:func:`fl_security.mtd.exposure.exposure_metrics`. No training is involved: the
quantities depend only on the scheduler and the adversary's knowledge.

Adversaries (budget ``b`` compromised clients):

* ``random`` – compromises ``b`` clients uniformly at random (no knowledge);
* ``predictive`` – compromises the ``b`` clients most often in its predicted schedule;
* ``just_in_time`` – compromises ``b`` members of each round's predicted cohort.

The prediction is the secret-free (public-seed) schedule.
"""
from __future__ import annotations

import os
import secrets
from contextlib import contextmanager

import numpy as np
import pandas as pd

from fl_security.evaluation.statistics import summarize_values
from fl_security.mtd.exposure import (
    exposure_metrics,
    just_in_time_assignment,
    predicted_schedule,
    predictive_set,
    schedule,
)


@contextmanager
def _temporary_mtd_secret(value: str | None):
    saved = os.environ.pop("FL_MTD_SECRET", None)
    if value is not None:
        os.environ["FL_MTD_SECRET"] = value
    try:
        yield
    finally:
        os.environ.pop("FL_MTD_SECRET", None)
        if saved is not None:
            os.environ["FL_MTD_SECRET"] = saved


def run_exposure_study(num_clients: int = 12, fraction: float = 0.34, rounds: int = 10,
                       budgets=(1, 2, 3), trials: int = 200) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for trial in range(trials):
        for schedule_name in ("static", "deterministic", "secret"):
            config = {"experiment": {"seed": trial}, "mtd": {"schedule": schedule_name}}
            secret = secrets.token_urlsafe(48) if schedule_name == "secret" else None
            with _temporary_mtd_secret(secret):
                actual = schedule(config, num_clients, rounds, fraction)
                predicted = predicted_schedule(config, num_clients, rounds, fraction)
            for budget in budgets:
                rng = np.random.default_rng(10_000 + trial)
                random_set = set(int(c) for c in rng.choice(num_clients, budget, replace=False))
                adversaries = {
                    "random": {r: random_set for r in actual},
                    "predictive": {r: predictive_set(predicted, budget, num_clients, trial) for r in actual},
                    "just_in_time": just_in_time_assignment(predicted, budget, num_clients, trial),
                }
                for adversary, assignment in adversaries.items():
                    metrics = exposure_metrics(actual, assignment, predicted)
                    rows.append({"trial": trial, "schedule": schedule_name, "adversary": adversary,
                                 "budget": budget, **metrics})
    raw = pd.DataFrame(rows)
    summary_rows = []
    metrics = [c for c in raw.columns if c not in {"trial", "schedule", "adversary", "budget", "rounds"}]
    for (schedule_name, adversary, budget), group in raw.groupby(["schedule", "adversary", "budget"]):
        for metric in metrics:
            summary_rows.append({"schedule": schedule_name, "adversary": adversary, "budget": budget,
                                 "metric": metric, **summarize_values(group[metric].tolist())})
    return raw, pd.DataFrame(summary_rows)
