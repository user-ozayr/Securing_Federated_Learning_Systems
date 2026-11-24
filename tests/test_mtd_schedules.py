"""Explicit MTD schedules and predictive-adversary exposure."""
import pytest

from fl_security.mtd.controller import MTDController
from fl_security.mtd.exposure import (
    exposure_metrics,
    just_in_time_assignment,
    predicted_schedule,
    predictive_set,
    schedule,
)

SECRET = "s" * 48


def _config(schedule_name, seed=7):
    return {"experiment": {"seed": seed}, "mtd": {"schedule": schedule_name}}


def _cohorts(config, rounds=6):
    return schedule(config, 12, rounds, 0.34)


def test_static_schedule_repeats_the_same_cohort(monkeypatch):
    monkeypatch.delenv("FL_MTD_SECRET", raising=False)
    cohorts = _cohorts(_config("static"))
    assert all(cohort == [0, 1, 2, 3] for cohort in cohorts.values())


def test_deterministic_schedule_changes_and_ignores_secret(monkeypatch):
    monkeypatch.delenv("FL_MTD_SECRET", raising=False)
    public = _cohorts(_config("deterministic"))
    monkeypatch.setenv("FL_MTD_SECRET", SECRET)
    with_secret_present = _cohorts(_config("deterministic"))
    assert public == with_secret_present
    assert len({tuple(c) for c in public.values()}) > 1


def test_secret_schedule_requires_secret_and_differs_from_public(monkeypatch):
    monkeypatch.delenv("FL_MTD_SECRET", raising=False)
    with pytest.raises(ValueError, match="FL_MTD_SECRET"):
        MTDController(_config("secret"))
    monkeypatch.setenv("FL_MTD_SECRET", "short")
    with pytest.raises(ValueError, match="32 bytes"):
        MTDController(_config("secret"))
    monkeypatch.setenv("FL_MTD_SECRET", SECRET)
    secret_a = _cohorts(_config("secret"), rounds=20)
    assert secret_a == _cohorts(_config("secret"), rounds=20)        # The same secret produces the same schedule.
    monkeypatch.setenv("FL_MTD_SECRET", "t" * 48)
    assert _cohorts(_config("secret"), rounds=20) != secret_a          # A different secret changes the schedule.
    assert MTDController(_config("secret")).generate_round_config(1, 12, 0.34)["secret_seeded"]


def test_invalid_schedule_name_is_rejected():
    with pytest.raises(ValueError):
        MTDController(_config("sometimes"))


def test_predictive_adversary_exploits_static_and_deterministic_schedules(monkeypatch):
    monkeypatch.setenv("FL_MTD_SECRET", SECRET)
    rounds = 30
    for name, expected_hit in (("static", 1.0), ("deterministic", 1.0)):
        config = _config(name)
        predicted = predicted_schedule(config, 12, rounds, 0.34)
        actual = schedule(config, 12, rounds, 0.34)
        assignment = just_in_time_assignment(predicted, 2, 12, seed=7)
        metrics = exposure_metrics(actual, assignment, predicted)
        assert metrics["prediction_accuracy"] == pytest.approx(1.0)
        assert metrics["compromise_hit_rate"] == pytest.approx(expected_hit)
    config = _config("secret")
    predicted = predicted_schedule(config, 12, rounds, 0.34)
    actual = schedule(config, 12, rounds, 0.34)
    assignment = just_in_time_assignment(predicted, 2, 12, seed=7)
    metrics = exposure_metrics(actual, assignment, predicted)
    assert metrics["prediction_accuracy"] < 0.7
    assert metrics["compromise_hit_rate"] < 0.7


def test_predictive_set_picks_most_frequent_predicted_clients():
    predicted = {1: [0, 1, 2, 3], 2: [0, 1, 4, 5], 3: [0, 6, 7, 8]}
    assert predictive_set(predicted, 2, 12, seed=1) == {0, 1}
