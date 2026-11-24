"""Post-run analysis of instrumented runs.

The instrumentation is an evaluation-only side channel: each simulated client
stores the update it submitted (after any attack), and the coordinator stores
the global model after each round. From these files this module computes, per
round:

* ``applied_update_norm`` – norm of the update actually applied to the model;
* ``deviation_from_honest`` – ||applied - honest-only FedAvg|| (absolute and
  relative): how far the round moved away from what honest clients alone
  would have produced with plain FedAvg;
* ``malicious_share_submitted`` / ``malicious_share_effective`` – share of the
  aggregate's mass contributed by malicious clients before and after the
  configured defence (coefficients recomputed with the exact reference);
* ``reference_max_abs_error`` – max |applied - recomputed aggregate| using the
  plaintext reference of the configured aggregation. For SPDZ2k runs this is an
  end-to-end correctness check of the secure computation inside real FL rounds.

The per-client files are packed into one compressed ``instrumentation.npz``.

Only entries of clients that the run itself recorded as selected in a round
(``selected_client_ids`` in the results CSV) are analysed. Entries of other
clients, which can only come from an earlier attempt in a reused run directory,
are ignored and counted (``instrumentation_ignored_entries``). A round whose
remaining entries do not match the recorded number of completed clients is
flagged (``instrumentation_consistent = 0``) and gets no metrics.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from fl_security.smpc.robust import (
    SecureDefenceConfig,
    decode_robust_output,
    robust_reference,
)


def _vector_norm(vector: np.ndarray) -> float:
    return float(np.linalg.norm(vector))


def _defence_config(config: dict) -> SecureDefenceConfig | None:
    smpc = config.get("smpc", {}) or {}
    raw = None
    if smpc.get("enabled") and (smpc.get("defence") or {}).get("enabled"):
        raw = smpc["defence"]
    reference = (config.get("defences", {}) or {}).get("norm_defence_reference") or {}
    if reference.get("enabled"):
        raw = reference
    return SecureDefenceConfig.from_mapping(raw) if raw else None


def _compute_defence_reference(
    config_obj: SecureDefenceConfig, ids, deltas, counts, direction=None
):
    """Recompute a defended round, applying its recorded direction screen when present."""
    order = sorted(range(len(ids)), key=lambda i: ids[i])
    weights = config_obj.quantized_weights([int(counts[i]) for i in order])
    spec = config_obj.round_spec(weights)
    inputs = [
        [int(v) for v in np.round(deltas[i] * config_obj.scale).astype(np.int64).tolist()]
        for i in order
    ]
    if direction is not None:
        values = [int(v) for v in np.asarray(direction).tolist()]
        result = robust_reference(inputs, weights, spec, direction_indices=values[1:],
                                  min_agree=values[0])
    else:
        result = robust_reference(inputs, weights, spec)
    decoded = decode_robust_output(result, weights, config_obj)
    coefficient = {}
    one_g = 1 << config_obj.clip_bits
    for position, index in enumerate(order):
        coefficient[ids[index]] = (
            result.accepted[position] * result.coefficients[position] * weights[position]
            / float(one_g)
        )
    applied = decoded.delta.numpy() if (decoded.output_check_passed and decoded.accepted_weight) else None
    return applied, coefficient, decoded


def _recorded_cohorts(frame: pd.DataFrame) -> dict[int, tuple[set[int], int | None]]:
    """Per round: the client ids the run selected and how many of them completed."""
    cohorts: dict[int, tuple[set[int], int | None]] = {}
    if "selected_client_ids" not in frame:
        return cohorts
    for _, row in frame.iterrows():
        text = row.get("selected_client_ids")
        if not isinstance(text, str) or not text.strip().startswith("["):
            continue
        completed = row.get("completed_clients")
        cohorts[int(row["round"])] = (
            {int(value) for value in json.loads(text)},
            None if completed is None or pd.isna(completed) else int(completed),
        )
    return cohorts


def _restrict_to_recorded_cohorts(rounds_data: dict, cohorts: dict) -> dict[int, dict]:
    """Drop instrumentation entries of clients outside each round's recorded cohort."""
    audit: dict[int, dict] = {}
    for round_num, (ids, deltas, flags, counts) in rounds_data.items():
        if round_num not in cohorts:
            continue
        cohort, completed = cohorts[round_num]
        keep = [index for index, client_id in enumerate(ids) if client_id in cohort]
        ignored = len(ids) - len(keep)
        for values in (ids, deltas, flags, counts):
            values[:] = [values[index] for index in keep]
        audit[round_num] = {
            "instrumentation_ignored_entries": ignored,
            "instrumentation_consistent": int(completed is None or len(keep) == completed),
        }
    return audit


def analyze_run(run_dir: Path, config: dict) -> dict:
    run_dir = Path(run_dir)
    instrumentation = next(run_dir.glob("*_instrumentation"), None)
    results = next(run_dir.glob("*_results.csv"))
    frame = pd.read_csv(results)
    summary: dict = {}
    last = frame[frame["round"] == frame["round"].max()].iloc[0]
    summary["final_accuracy"] = float(last["global_accuracy"])
    summary["final_loss"] = float(last["global_loss"])
    if "backdoor_asr" in frame and not pd.isna(last.get("backdoor_asr")):
        summary["final_backdoor_asr"] = float(last["backdoor_asr"])
    if instrumentation is None:
        return summary

    rounds_data: dict[int, tuple[list, list, list, list]] = {}
    for path in sorted(instrumentation.glob("r*_c*.npz")):
        with np.load(path) as data:
            ids, deltas, flags, counts = rounds_data.setdefault(
                int(path.name[1:5]), ([], [], [], [])
            )
            ids.append(int(path.name.split("_c")[1][:4]))
            deltas.append(data["delta"].astype(np.float64))
            flags.append(bool(data["malicious"]))
            counts.append(int(data["num_examples"]))
    globals_ = {int(p.name[1:5]): np.load(p) for p in instrumentation.glob("r*_global.npy")}
    directions = {int(p.name[1:5]): np.load(p) for p in instrumentation.glob("r*_direction.npy")}
    audit = _restrict_to_recorded_cohorts(rounds_data, _recorded_cohorts(frame))
    summary.update(_summarize_rows(
        run_dir, _round_rows(rounds_data, globals_, config, audit, directions)))
    # Pack the per-client files into one archive (raw evidence) and remove them.
    arrays = {}
    for path in sorted(instrumentation.iterdir()):
        if path.suffix == ".npz":
            with np.load(path) as data:
                for key in data.files:
                    arrays[f"{path.stem}__{key}"] = data[key]
        elif path.suffix == ".npy":
            arrays[path.stem] = np.load(path)
    np.savez_compressed(run_dir / "instrumentation.npz", **arrays)
    shutil.rmtree(instrumentation)
    return summary


def reanalyze_packed(run_dir: Path, config: dict) -> dict:
    """Recompute round_analysis.csv from a packed instrumentation.npz."""
    run_dir = Path(run_dir)
    packed = load_instrumentation(run_dir / "instrumentation.npz")
    rounds_data: dict[int, tuple[list, list, list, list]] = {}
    globals_, directions = {}, {}
    for key, value in packed.items():
        if key.endswith("_global"):
            globals_[int(key[1:5])] = value
        elif key.endswith("_direction"):
            directions[int(key[1:5])] = value
        elif key.endswith("__delta"):
            stem = key[: -len("__delta")]
            ids, deltas, flags, counts = rounds_data.setdefault(int(stem[1:5]), ([], [], [], []))
            ids.append(int(stem.split("_c")[1][:4]))
            deltas.append(value.astype(np.float64))
            flags.append(bool(packed[f"{stem}__malicious"]))
            counts.append(int(packed[f"{stem}__num_examples"]))
    for ids, deltas, flags, counts in rounds_data.values():
        order = sorted(range(len(ids)), key=lambda i: ids[i])
        for values in (ids, deltas, flags, counts):
            values[:] = [values[i] for i in order]
    results = next(run_dir.glob("*_results.csv"), None)
    cohorts = _recorded_cohorts(pd.read_csv(results)) if results is not None else {}
    audit = _restrict_to_recorded_cohorts(rounds_data, cohorts)
    return _summarize_rows(run_dir, _round_rows(rounds_data, globals_, config, audit, directions))


def _summarize_rows(run_dir: Path, rows: list[dict]) -> dict:
    summary: dict = {}
    if rows:
        table = pd.DataFrame(rows)
        table.to_csv(run_dir / "round_analysis.csv", index=False)
        for column in ("deviation_from_honest_relative", "malicious_share_effective",
                       "malicious_share_submitted", "reference_max_abs_error",
                       "reference_relative_error"):
            if column in table:
                values = table[column].dropna()
                if len(values):
                    summary[f"mean_{column}"] = float(values.mean())
                    if column.startswith("reference_"):
                        summary[f"max_{column}"] = float(values.max())
        if "instrumentation_ignored_entries" in table:
            summary["instrumentation_ignored_entries"] = int(
                table["instrumentation_ignored_entries"].fillna(0).sum())
            summary["instrumentation_inconsistent_rounds"] = int(
                (table["instrumentation_consistent"].fillna(1) == 0).sum())
    return summary


def _round_rows(rounds_data: dict, globals_: dict, config: dict, audit: dict | None = None,
                directions: dict | None = None) -> list[dict]:
    defence = _defence_config(config)
    directions = directions or {}
    screened = defence is not None and defence.direction_check
    smpc = config.get("smpc", {}) or {}
    sum_only = bool(smpc.get("enabled")) and defence is None
    rows = []
    for round_num in sorted(rounds_data):
        ids, deltas, flags, counts = rounds_data[round_num]
        if round_num not in globals_ or round_num - 1 not in globals_:
            continue
        check = (audit or {}).get(round_num, {})
        if not ids or (check and not check["instrumentation_consistent"]):
            # the entries do not match what the run recorded: no metrics for this round
            rows.append({"round": round_num, "participants": len(ids), **check})
            continue
        applied = globals_[round_num] - globals_[round_num - 1]
        weights = np.asarray(counts, dtype=np.float64)
        stacked = np.stack(deltas)
        honest = [i for i, flag in enumerate(flags) if not flag]
        malicious = [i for i, flag in enumerate(flags) if flag]
        row = {"round": round_num, "participants": len(ids), "malicious": len(malicious),
               "applied_update_norm": _vector_norm(applied)}
        all_fedavg = (weights[:, None] * stacked).sum(0) / weights.sum()
        if honest:
            honest_fedavg = (weights[honest, None] * stacked[honest]).sum(0) / weights[honest].sum()
            reference_norm = max(_vector_norm(honest_fedavg), 1e-12)
            row["deviation_from_honest"] = _vector_norm(applied - honest_fedavg)
            row["deviation_from_honest_relative"] = row["deviation_from_honest"] / reference_norm
            row["cosine_with_honest"] = float(
                np.dot(applied, honest_fedavg) / max(_vector_norm(applied) * reference_norm, 1e-12))
        def weighted_update_norm(
            indices: list[int], coefficients: dict[int, float], updates: np.ndarray
        ) -> float:
            if not indices:
                return 0.0
            weighted_update = sum(coefficients[index] * updates[index] for index in indices)
            return _vector_norm(weighted_update)

        submitted = {i: weights[i] for i in range(len(ids))}
        m = weighted_update_norm(malicious, submitted, stacked)
        h = weighted_update_norm(honest, submitted, stacked)
        row["malicious_share_submitted"] = m / (m + h) if (m + h) > 0 else 0.0
        if screened and round_num not in directions:
            # This secret subset was not recorded, so the round cannot be recomputed.
            # Leave the reference-error fields unset.
            row["reference_kind"] = "robust_reference_unavailable"
            row.update(check)
            rows.append(row)
            continue
        if defence is not None:
            recomputed, coefficient, decoded = _compute_defence_reference(
                defence, ids, stacked, counts, directions.get(round_num) if screened else None)
            effective = {i: coefficient[ids[i]] for i in range(len(ids))}
            m = weighted_update_norm(malicious, effective, stacked)
            h = weighted_update_norm(honest, effective, stacked)
            row["malicious_share_effective"] = m / (m + h) if (m + h) > 0 else 0.0
            row["reference_output_check_passed"] = int(decoded.output_check_passed)
            reference = recomputed if recomputed is not None else np.zeros_like(applied)
        else:
            row["malicious_share_effective"] = row["malicious_share_submitted"]
            reference = all_fedavg
        if not (config.get("defences", {}) or {}).get("robust_aggregation", {}).get("enabled"):
            row["reference_max_abs_error"] = float(np.max(np.abs(applied - reference)))
            # float32 model arithmetic: the achievable absolute agreement scales
            # with the magnitude of the model parameters
            row["reference_relative_error"] = _vector_norm(applied - reference) / max(_vector_norm(reference), 1e-12)
            row["global_max_abs"] = float(np.max(np.abs(globals_[round_num])))
        row["reference_kind"] = (
            "robust_reference" if defence is not None else ("fedavg_fixed_point" if sum_only else "fedavg")
        )
        row.update(check)
        rows.append(row)
    return rows


def load_instrumentation(path: Path) -> dict:
    """Inverse of the packing step, for re-analysis of archived runs."""
    with np.load(path) as data:
        return {key: data[key] for key in data.files}


__all__ = ["analyze_run", "load_instrumentation"]
