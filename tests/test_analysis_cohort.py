"""Post-run analysis uses only the cohort a run recorded; repeated runs start clean."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fl_security.experiments.analysis import _recorded_cohorts, reanalyze_packed
from fl_security.experiments.suite import set_aside_previous_attempt

PLAIN_FEDAVG = {"smpc": {"enabled": False}, "federated_learning": {"num_clients": 12}}


def _write_run(run_dir: Path, entries: dict[int, list[int]], cohort: dict[int, list[int]],
               completed: dict[int, int]) -> None:
    """A packed run whose global model applied plain FedAvg over ``cohort``."""
    rng = np.random.default_rng(0)
    run_dir.mkdir(parents=True)
    model = np.zeros(5, dtype=np.float32)
    arrays = {"r0000_global": model.copy()}
    rows = [{"round": 0, "global_accuracy": 0.1, "global_loss": 2.3,
             "selected_client_ids": "[]", "completed_clients": 0}]
    for round_num in sorted(entries):
        deltas = {cid: rng.normal(size=5).astype(np.float32) for cid in entries[round_num]}
        for cid, delta in deltas.items():
            stem = f"r{round_num:04d}_c{cid:04d}"
            arrays[f"{stem}__delta"] = delta
            arrays[f"{stem}__malicious"] = np.array(False)
            arrays[f"{stem}__num_examples"] = np.array(10)
        applied = [deltas[cid] for cid in cohort[round_num] if cid in deltas]
        model = (model + np.mean(applied, axis=0)).astype(np.float32)
        arrays[f"r{round_num:04d}_global"] = model.copy()
        rows.append({"round": round_num, "global_accuracy": 0.5, "global_loss": 1.0,
                     "selected_client_ids": json.dumps(sorted(cohort[round_num])),
                     "completed_clients": completed[round_num]})
    pd.DataFrame(rows).to_csv(run_dir / "run_results.csv", index=False)
    np.savez_compressed(run_dir / "instrumentation.npz", **arrays)


def test_reanalysis_ignores_entries_outside_the_recorded_cohort(tmp_path):
    run_dir = tmp_path / "run"
    # Client 7's entry is left over from an earlier attempt with a different cohort.
    _write_run(run_dir, entries={1: [0, 1, 7]}, cohort={1: [0, 1]}, completed={1: 2})
    summary = reanalyze_packed(run_dir, PLAIN_FEDAVG)
    row = pd.read_csv(run_dir / "round_analysis.csv").iloc[0]
    assert row["participants"] == 2
    assert row["instrumentation_ignored_entries"] == 1
    assert row["instrumentation_consistent"] == 1
    assert row["reference_max_abs_error"] < 1e-6
    assert summary["instrumentation_ignored_entries"] == 1
    assert summary["instrumentation_inconsistent_rounds"] == 0


def test_round_with_unexpected_entry_count_is_flagged_without_metrics(tmp_path):
    run_dir = tmp_path / "run"
    # the run recorded three completed clients, but only two entries exist
    _write_run(run_dir, entries={1: [0, 1]}, cohort={1: [0, 1, 2]}, completed={1: 3})
    summary = reanalyze_packed(run_dir, PLAIN_FEDAVG)
    row = pd.read_csv(run_dir / "round_analysis.csv").iloc[0]
    assert row["instrumentation_consistent"] == 0
    assert "reference_max_abs_error" not in row or pd.isna(row["reference_max_abs_error"])
    assert summary["instrumentation_inconsistent_rounds"] == 1


def test_runs_without_recorded_cohorts_are_not_filtered():
    frame = pd.DataFrame({"round": [0, 1], "global_accuracy": [0.1, 0.2]})
    assert _recorded_cohorts(frame) == {}


def test_repeated_run_starts_from_an_empty_directory(tmp_path):
    output_root = tmp_path / "experiments"
    run_dir = output_root / "runs" / "e1" / "e1__x__s101"
    run_dir.mkdir(parents=True)
    (run_dir / "e1__x__s101_abort.json").write_text("{}", encoding="utf-8")
    moved = set_aside_previous_attempt(run_dir, output_root, "e1")
    assert moved is not None and not run_dir.exists()
    assert (moved / "e1__x__s101_abort.json").read_text(encoding="utf-8") == "{}"
    assert moved.parents[2] == output_root / "failed_attempts"
    assert set_aside_previous_attempt(run_dir, output_root, "e1") is None
    empty = output_root / "runs" / "e1" / "e1__y__s101"
    empty.mkdir(parents=True)
    assert set_aside_previous_attempt(empty, output_root, "e1") is None and empty.exists()
