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
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from fl_security.smpc.robust import (
    SecureDefenceConfig,
    decode_robust_output,
    robust_reference,
)


def _norm(vector: np.ndarray) -> float:
    return float(np.linalg.norm(vector))


def _defence(config: dict) -> SecureDefenceConfig | None:
    smpc = config.get("smpc", {}) or {}
    raw = None
    if smpc.get("enabled") and (smpc.get("defence") or {}).get("enabled"):
        raw = smpc["defence"]
    reference = (config.get("defences", {}) or {}).get("norm_defence_reference") or {}
    if reference.get("enabled"):
        raw = reference
    return SecureDefenceConfig.from_mapping(raw) if raw else None


def _defended(config_obj: SecureDefenceConfig, ids, deltas, counts):
    order = sorted(range(len(ids)), key=lambda i: ids[i])
    weights = config_obj.quantized_weights([int(counts[i]) for i in order])
    spec = config_obj.round_spec(weights)
    inputs = [
        [int(v) for v in np.round(deltas[i] * config_obj.scale).astype(np.int64).tolist()]
        for i in order
    ]
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

    defence = _defence(config)
    smpc = config.get("smpc", {}) or {}
    sum_only = bool(smpc.get("enabled")) and defence is None
    rows = []
    rounds = sorted({int(p.name[1:5]) for p in instrumentation.glob("r*_c*.npz")})
    globals_ = {int(p.name[1:5]): np.load(p) for p in instrumentation.glob("r*_global.npy")}
    for round_num in rounds:
        files = sorted(instrumentation.glob(f"r{round_num:04d}_c*.npz"))
        ids, deltas, flags, counts = [], [], [], []
        for path in files:
            data = np.load(path)
            ids.append(int(path.name.split("_c")[1][:4]))
            deltas.append(data["delta"].astype(np.float64))
            flags.append(bool(data["malicious"]))
            counts.append(int(data["num_examples"]))
        if round_num not in globals_ or round_num - 1 not in globals_:
            continue
        applied = globals_[round_num] - globals_[round_num - 1]
        weights = np.asarray(counts, dtype=np.float64)
        stacked = np.stack(deltas)
        honest = [i for i, flag in enumerate(flags) if not flag]
        malicious = [i for i, flag in enumerate(flags) if flag]
        row = {"round": round_num, "participants": len(ids), "malicious": len(malicious),
               "applied_update_norm": _norm(applied)}
        all_fedavg = (weights[:, None] * stacked).sum(0) / weights.sum()
        if honest:
            honest_fedavg = (weights[honest, None] * stacked[honest]).sum(0) / weights[honest].sum()
            reference_norm = max(_norm(honest_fedavg), 1e-12)
            row["deviation_from_honest"] = _norm(applied - honest_fedavg)
            row["deviation_from_honest_relative"] = row["deviation_from_honest"] / reference_norm
            row["cosine_with_honest"] = float(
                np.dot(applied, honest_fedavg) / max(_norm(applied) * reference_norm, 1e-12))
        mass = lambda idx, coef: _norm(sum(coef[i] * stacked[i] for i in idx)) if idx else 0.0  # noqa: E731
        submitted = {i: weights[i] for i in range(len(ids))}
        m, h = mass(malicious, submitted), mass(honest, submitted)
        row["malicious_share_submitted"] = m / (m + h) if (m + h) > 0 else 0.0
        if defence is not None:
            recomputed, coefficient, decoded = _defended(defence, ids, stacked, counts)
            effective = {i: coefficient[ids[i]] for i in range(len(ids))}
            m, h = mass(malicious, effective), mass(honest, effective)
            row["malicious_share_effective"] = m / (m + h) if (m + h) > 0 else 0.0
            row["reference_output_check_passed"] = int(decoded.output_check_passed)
            reference = recomputed if recomputed is not None else np.zeros_like(applied)
        else:
            row["malicious_share_effective"] = row["malicious_share_submitted"]
            reference = all_fedavg
        if not (config.get("defences", {}) or {}).get("robust_aggregation", {}).get("enabled"):
            row["reference_max_abs_error"] = float(np.max(np.abs(applied - reference)))
        row["reference_kind"] = (
            "robust_reference" if defence is not None else ("fedavg_fixed_point" if sum_only else "fedavg")
        )
        rows.append(row)
    if rows:
        table = pd.DataFrame(rows)
        table.to_csv(run_dir / "round_analysis.csv", index=False)
        for column in ("deviation_from_honest_relative", "malicious_share_effective",
                       "malicious_share_submitted", "reference_max_abs_error"):
            if column in table:
                values = table[column].dropna()
                if len(values):
                    summary[f"mean_{column}"] = float(values.mean())
                    if column == "reference_max_abs_error":
                        summary["max_reference_max_abs_error"] = float(values.max())
    # Pack the per-client files into one archive (raw evidence) and remove them.
    arrays = {}
    for path in sorted(instrumentation.iterdir()):
        if path.suffix == ".npz":
            data = np.load(path)
            for key in data.files:
                arrays[f"{path.stem}__{key}"] = data[key]
        elif path.suffix == ".npy":
            arrays[path.stem] = np.load(path)
    np.savez_compressed(run_dir / "instrumentation.npz", **arrays)
    shutil.rmtree(instrumentation)
    return summary


def load_instrumentation(path: Path) -> dict:
    """Inverse of the packing step, for re-analysis of archived runs."""
    with np.load(path) as data:
        return {key: data[key] for key in data.files}


__all__ = ["analyze_run", "load_instrumentation"]
_ = (json, math, torch)
