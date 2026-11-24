"""Paired evaluation: conditions of one (study, seed) share their MTD secret."""
import os
import stat

import pytest

from fl_security.experiments.grid import STUDIES
from fl_security.experiments.suite import load_pairing_key, paired_secret
from fl_security.mtd.controller import MTDController


def test_pairing_key_is_created_once_and_private(tmp_path):
    key = load_pairing_key(tmp_path)
    assert len(key) == 32 and load_pairing_key(tmp_path) == key
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "pairing_key").stat().st_mode) == 0o600
    (tmp_path / "pairing_key").write_text("00")
    with pytest.raises(ValueError):
        load_pairing_key(tmp_path)


def test_paired_secret_depends_on_study_and_seed_only():
    key = b"p" * 32
    secret = paired_secret(key, "p3", 101)
    assert len(secret.encode()) >= 32 and secret == paired_secret(key, "p3", 101)
    assert secret != paired_secret(key, "p3", 102)
    assert secret != paired_secret(key, "m3", 101)
    assert secret != paired_secret(b"q" * 32, "p3", 101)


def test_p3_conditions_of_a_seed_draw_identical_cohorts(monkeypatch):
    runs = STUDIES["p3"]()
    assert len(runs) == 4 * 4 * 5 and all(r.tags["paired"] for r in runs)
    assert not any(r.tags.get("paired") for r in STUDIES["m3"]())
    by_seed = {}
    for run in (r for r in runs if r.needs_secret):
        monkeypatch.setenv("FL_MTD_SECRET", paired_secret(b"p" * 32, run.study, run.seed))
        fl = run.config["federated_learning"]
        cohorts = tuple(tuple(MTDController(run.config).generate_round_config(
            r, fl["num_clients"], fl["fraction_train"])["selected_clients"]) for r in range(1, 11))
        by_seed.setdefault(run.seed, set()).add(cohorts)
    assert len(by_seed) == 5 and all(len(c) == 1 for c in by_seed.values())


def test_secret_subset_runs_are_marked():
    runs = {r.condition: r for r in STUDIES["p3"]() if r.seed == 101 and r.attack == "none"}
    assert runs["reference_direction_secret_t52"].uses_secret_subset
    assert runs["reference_direction_secret_mtd_t52"].uses_secret_subset
    assert not runs["reference_defence"].uses_secret_subset
    assert not runs["reference_defence"].needs_secret
