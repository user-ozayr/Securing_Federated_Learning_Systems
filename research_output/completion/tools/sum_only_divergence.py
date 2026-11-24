"""Trace why sum-only SPDZ2k and plaintext FedAvg take different paths.

The script reads each run's packed instrumentation, rebuilds the submitted
client models from the previous global model and each recorded update, and
checks that the reconstruction is exact in float32. It then computes each
round with both aggregation rules:

* Sum-only SPDZ2k: round float64(w) * n * S to int64, add the integers, divide
  by S and N in float64, then cast to float32. This mirrors
  mp_spdz._encode_weighted_model and mp_spdz.receive_weighted_average.
* Plaintext FedAvg: sum float64(w) * n, divide by N, then cast to float32.
  This mirrors aggregation.weighted_fedavg.

The script writes these files under <output_dir>:

* sum_only_round_exactness.csv compares each applied global model with both
  arithmetic results for every sum-only SPDZ2k round.
* fedavg_round_exactness.csv checks that the FedAvg emulation reproduces every
  recorded plaintext round.
* pair_divergence.csv compares same-attack, same-seed E1 pairs
  (smpc_only/baseline) with static cohorts. It records cohort, input, and
  previous-model matches, model distance, and metric differences.
* replay_comparison.csv compares plaintext replays from sum_only_replay.py
  with their reference runs. The file is written when <output_dir>/replays
  exists.
* robust_round_exactness.csv applies the same bit-level check to robust SPDZ2k
  and plaintext rounds, comparing each recorded model with an exact plaintext
  replication using robust_reference, decoding, and apply_delta.
* summary.txt contains the aggregate findings.

Run from the repository root. Set PYTHONPATH=src to enable the robust check:

    python sum_only_divergence.py <completion_root> <output_dir>
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

BANDS = ((0.0, 1e-4), (1e-4, 1e-3), (1e-3, 1e-2), (1e-2, 1e-1), (1e-1, np.inf))
BAND_LABELS = ("<1e-4", "1e-4..1e-3", "1e-3..1e-2", "1e-2..1e-1", ">=1e-1")


# ---- loading ----------------------------------------------------------------------
def load_run(run_dir: Path):
    with np.load(run_dir / "instrumentation.npz") as data:
        packed = {key: data[key] for key in data.files}
    globals_ = {int(key[1:5]): value.astype(np.float64)
                for key, value in packed.items() if key.endswith("_global")}
    entries: dict[int, dict[int, tuple[np.ndarray, int, bool]]] = {}
    for key, value in packed.items():
        if key.endswith("__delta"):
            stem = key[: -len("__delta")]
            entries.setdefault(int(stem[1:5]), {})[int(stem.split("_c")[1][:4])] = (
                value.astype(np.float64),
                int(packed[f"{stem}__num_examples"]),
                bool(packed[f"{stem}__malicious"]),
            )
    frame = pd.read_csv(next(run_dir.glob("*_results.csv"))).sort_values("round")
    config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
    return globals_, entries, frame.reset_index(drop=True), config


def recorded_cohort(frame: pd.DataFrame, round_num: int) -> list[int] | None:
    row = frame[frame["round"] == round_num]
    if row.empty:
        return None
    text = row.iloc[0].get("selected_client_ids")
    if not isinstance(text, str) or not text.strip().startswith("["):
        return None
    return [int(value) for value in json.loads(text)]


def classify_run(config: dict) -> str:
    smpc = config.get("smpc", {}) or {}
    defences = config.get("defences", {}) or {}
    if smpc.get("enabled"):
        return "spdz2k_robust" if (smpc.get("defence") or {}).get("enabled") else "spdz2k_sum_only"
    if (defences.get("norm_defence_reference") or {}).get("enabled"):
        return "plaintext_robust"
    if (defences.get("robust_aggregation") or {}).get("enabled"):
        return "plaintext_detector"
    return "fedavg"


# ---- arithmetic emulations ----------------------------------------------------------
def rebuild_client_states(previous: np.ndarray, entries: dict, cohort: list[int]):
    states, counts, exact = [], [], True
    for client_id in cohort:
        delta, count, _ = entries[client_id]
        value = previous + delta
        state = value.astype(np.float32)
        exact &= bool(np.array_equal(state.astype(np.float64), value))
        states.append(state)
        counts.append(count)
    return states, counts, exact


def sum_only_fixed_point(states, counts, scale: int):
    """Emulate sum-only SPDZ2k by encoding each client, adding, and decoding."""
    total = sum(counts)
    accumulator = np.zeros(states[0].shape, dtype=np.int64)
    peak = 0
    for state, count in zip(states, counts):
        # Production encoding converts to float64, multiplies by n, then rounds v * S.
        scaled = np.round(state.astype(np.float64) * count * scale)
        if np.any(np.abs(scaled) >= 2.0 ** 63):
            raise OverflowError("fixed-point value exceeds int64 range")
        encoded = scaled.astype(np.int64)
        peak = max(peak, int(np.abs(encoded).max()))
        accumulator += encoded
    # Production decoding divides the float64 sum by S and N, then casts to the model dtype.
    value = accumulator.astype(np.float64) / scale / total
    return value.astype(np.float32), value, peak


def plaintext_fedavg(states, counts, order=None):
    """Match aggregation.weighted_fedavg: sum float64(w) * n in order, divide by N, and cast to float32."""
    total = sum(counts)
    summed = np.zeros(states[0].shape, dtype=np.float64)
    for index in (order if order is not None else range(len(states))):
        summed += states[index].astype(np.float64) * counts[index]
    value = summed / total
    return value.astype(np.float32), value


def ordered_bits(values: np.ndarray) -> np.ndarray:
    bits = values.view(np.int32).astype(np.int64)
    return np.where(bits < 0, -(1 << 31) - bits, bits)


def ulp_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs(ordered_bits(a) - ordered_bits(b))


def float32_ties(value: np.ndarray) -> np.ndarray:
    """Return a mask for float64 values halfway between two float32 values."""
    rounded = value.astype(np.float32)
    error = value - rounded.astype(np.float64)
    direction = np.where(error > 0, np.float32(np.inf), np.float32(-np.inf)).astype(np.float32)
    neighbour = np.nextafter(rounded, direction)
    spacing = np.abs(neighbour.astype(np.float64) - rounded.astype(np.float64))
    return (error != 0) & (np.abs(error) * 2 == spacing)


def band_counts(mask: np.ndarray, magnitude: np.ndarray) -> dict:
    out = {}
    for label, (low, high) in zip(BAND_LABELS, BANDS):
        in_band = (magnitude >= low) & (magnitude < high)
        out[label] = [int((mask & in_band).sum()), int(in_band.sum())]
    return out


# ---- per-run checks -----------------------------------------------------------------
def round_checks(run_dir: Path, run_kind: str) -> list[dict]:
    globals_, entries, frame, config = load_run(run_dir)
    scale = int((config.get("smpc", {}) or {}).get("fixed_point_scale", 1_000_000))
    max_clients = int(config["federated_learning"]["num_clients"])
    ring_limit = (1 << 62) // max_clients
    rows = []
    for round_num in sorted(entries):
        if round_num not in globals_ or round_num - 1 not in globals_:
            continue
        cohort = recorded_cohort(frame, round_num)
        if cohort is None or any(client_id not in entries[round_num] for client_id in cohort):
            rows.append({"run_id": run_dir.name, "round": round_num, "note": "cohort entries missing"})
            continue
        states, counts, exact = rebuild_client_states(globals_[round_num - 1], entries[round_num], cohort)
        applied = globals_[round_num].astype(np.float32)
        fa32, fa64 = plaintext_fedavg(states, counts)
        try:
            fp32, fp64, peak = sum_only_fixed_point(states, counts, scale)
        except OverflowError:
            # This occurs only after a plaintext model diverges; the sum-only encoder rejects these values.
            rows.append({"run_id": run_dir.name, "kind": run_kind, "round": round_num,
                         "note": "inputs exceed the int64 fixed-point range"})
            continue
        fp_ulps, fa_ulps = ulp_distance(applied, fp32), ulp_distance(applied, fa32)
        order_note = "cohort order"
        if run_kind == "fedavg" and (fa_ulps > 0).any():
            best = None
            for order in itertools.permutations(range(len(states))):
                candidate, _ = plaintext_fedavg(states, counts, order)
                mismatches = int((ulp_distance(applied, candidate) > 0).sum())
                if best is None or mismatches < best[0]:
                    best = (mismatches, order)
                if mismatches == 0:
                    break
            order_note = f"best of {len(states)}! orders: {best[1]}"
            fa32, _ = plaintext_fedavg(states, counts, best[1])
            fa_ulps = ulp_distance(applied, fa32)
        magnitude = np.abs(applied.astype(np.float64))
        fa_mask = fa_ulps > 0
        ties = float32_ties(fa64)
        rows.append({
            "run_id": run_dir.name,
            "kind": run_kind,
            "round": round_num,
            "participants": len(cohort),
            "total_examples": sum(counts),
            "coordinates": int(applied.size),
            "inputs_reconstructed_exactly": exact,
            "fixed_point_scale": scale,
            "applied_vs_fixed_point_mismatches": int((fp_ulps > 0).sum()),
            "applied_vs_fixed_point_max_ulps": int(fp_ulps.max()),
            "applied_vs_fedavg_mismatches": int(fa_mask.sum()),
            "applied_vs_fedavg_max_ulps": int(fa_ulps.max()),
            "applied_vs_fedavg_max_abs": float(np.max(np.abs(applied.astype(np.float64) - fa32.astype(np.float64)))),
            "fedavg_order": order_note,
            "fedavg_value_at_float32_tie": int(ties.sum()),
            "applied_vs_fedavg_mismatches_at_tie": int((fa_mask & ties).sum()),
            "applied_vs_fedavg_mismatches_off_tie": int((fa_mask & ~ties).sum()),
            "fixed_point_vs_fedavg_mismatches": int((ulp_distance(fp32, fa32) > 0).sum()),
            "precast_max_abs_fixed_point_minus_fedavg": float(np.max(np.abs(fp64 - fa64))),
            "quantization_bound": len(counts) * 0.5 / scale / sum(counts),
            "fedavg_mismatches_by_magnitude": json.dumps(band_counts(fa_mask, magnitude)),
            "max_abs_parameter": float(magnitude.max()),
            "encoded_peak_abs": peak,
            "ring_limit": ring_limit,
        })
    return rows


def robust_checks(run_dir: Path, run_kind: str) -> list[dict]:
    """Compare recorded robust-program models with an exact plaintext replay of each round.

    Replication: robust_reference on the encoded recorded updates, decoding, and
    apply_delta (float64(previous) + delta, cast to float32), as in the strategy.
    """
    from fl_security.experiments.analysis import _compute_defence_reference, _defence_config

    globals_, entries, frame, config = load_run(run_dir)
    defence = _defence_config(config)
    rows = []
    for round_num in sorted(entries):
        if round_num not in globals_ or round_num - 1 not in globals_:
            continue
        cohort = recorded_cohort(frame, round_num)
        if cohort is None or any(client_id not in entries[round_num] for client_id in cohort):
            rows.append({"run_id": run_dir.name, "kind": run_kind, "round": round_num,
                         "note": "cohort entries missing"})
            continue
        deltas = np.stack([entries[round_num][client_id][0] for client_id in cohort])
        counts = [entries[round_num][client_id][1] for client_id in cohort]
        applied_delta, _, _ = _compute_defence_reference(defence, list(cohort), deltas, counts)
        previous = globals_[round_num - 1]
        expected = (previous + applied_delta if applied_delta is not None else previous).astype(np.float32)
        ulps = ulp_distance(globals_[round_num].astype(np.float32), expected)
        rows.append({"run_id": run_dir.name, "kind": run_kind, "round": round_num,
                     "participants": len(cohort), "update_applied": applied_delta is not None,
                     "applied_vs_reference_mismatches": int((ulps > 0).sum()),
                     "applied_vs_reference_max_ulps": int(ulps.max())})
    return rows


def run_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [c for c in ("round", "global_accuracy", "global_loss", "backdoor_asr") if c in frame]
    return frame[columns].set_index("round")


def pair_rows(dir_a: Path, dir_b: Path, label_a: str, label_b: str, scale: int) -> list[dict]:
    ga, ea, fa_frame, _ = load_run(dir_a)
    gb, eb, fb_frame, _ = load_run(dir_b)
    ma, mb = run_metrics(fa_frame), run_metrics(fb_frame)
    rows = []
    for round_num in sorted((set(ga) & set(gb)) - {0}):
        cohort_a, cohort_b = recorded_cohort(fa_frame, round_num), recorded_cohort(fb_frame, round_num)
        cohort_equal = cohort_a is not None and cohort_a == cohort_b
        previous_equal = bool(np.array_equal(ga[round_num - 1], gb[round_num - 1]))
        inputs_equal = cohort_equal and all(
            client_id in ea.get(round_num, {}) and client_id in eb.get(round_num, {})
            and np.array_equal(ea[round_num][client_id][0], eb[round_num][client_id][0])
            and ea[round_num][client_id][1] == eb[round_num][client_id][1]
            for client_id in cohort_a
        )
        a32, b32 = ga[round_num].astype(np.float32), gb[round_num].astype(np.float32)
        difference = ga[round_num] - gb[round_num]
        row = {
            f"run_{label_a}": dir_a.name, f"run_{label_b}": dir_b.name, "round": round_num,
            "cohort_equal": cohort_equal, "previous_global_equal": previous_equal,
            "inputs_equal": inputs_equal,
            "global_mismatched_coordinates": int((ulp_distance(a32, b32) > 0).sum()),
            "global_max_abs_difference": float(np.max(np.abs(difference))),
            "global_l2_difference": float(np.linalg.norm(difference)),
            f"update_l2_{label_b}": float(np.linalg.norm(gb[round_num] - gb[round_num - 1])),
        }
        if inputs_equal and previous_equal:
            states, counts, _ = rebuild_client_states(ga[round_num - 1], ea[round_num], cohort_a)
            fp32, _, _ = sum_only_fixed_point(states, counts, scale)
            fa32, _ = plaintext_fedavg(states, counts)
            row[f"{label_a}_equals_fixed_point"] = bool((ulp_distance(a32, fp32) == 0).all())
            row[f"{label_b}_equals_fedavg"] = bool((ulp_distance(b32, fa32) == 0).all())
        for metric in ("global_accuracy", "global_loss", "backdoor_asr"):
            if metric in ma and metric in mb and round_num in ma.index and round_num in mb.index:
                value = ma.at[round_num, metric] - mb.at[round_num, metric]
                row[f"{metric}_difference"] = None if pd.isna(value) else float(value)
        rows.append(row)
    return rows


def replay_rows(output_dir: Path, runs_root: Path) -> list[dict]:
    rows = []
    for metadata_path in sorted((output_dir / "replays").glob("*/replay_metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        replay_dir = metadata_path.parent
        if metadata.get("status") != "completed" or not (replay_dir / "instrumentation.npz").exists():
            rows.append({"replay": replay_dir.name, "status": metadata.get("status")})
            continue
        g_replay, _, frame_replay, _ = load_run(replay_dir)
        m_replay = run_metrics(frame_replay)
        for target_label, target in sorted(metadata.get("compare_with", {}).items()):
            target_dir = runs_root / target
            g_target, _, frame_target, _ = load_run(target_dir)
            m_target = run_metrics(frame_target)
            rounds = sorted((set(g_replay) & set(g_target)) - {0})
            mismatched = {r: int((ulp_distance(g_replay[r].astype(np.float32),
                                               g_target[r].astype(np.float32)) > 0).sum()) for r in rounds}
            differing = [r for r in rounds if mismatched[r] > 0]
            metric_rounds = sorted(set(m_replay.index) & set(m_target.index))
            metric_equal = all(
                (pd.isna(m_replay.at[r, c]) and pd.isna(m_target.at[r, c])) or m_replay.at[r, c] == m_target.at[r, c]
                for r in metric_rounds for c in m_replay.columns if c in m_target.columns)
            accuracy = (m_replay["global_accuracy"] - m_target["global_accuracy"]).abs().dropna()
            rows.append({
                "replay": replay_dir.name, "scale": metadata.get("scale"), "compared_with": target_label,
                "target_run": target, "rounds": len(rounds),
                "rounds_with_identical_global_model": len(rounds) - len(differing),
                "first_round_with_different_global_model": differing[0] if differing else None,
                "mismatched_coordinates_per_round": json.dumps([mismatched[r] for r in rounds]),
                "metrics_identical_in_all_rounds": metric_equal,
                "max_abs_accuracy_difference": float(accuracy.max()) if len(accuracy) else None,
            })
    return rows


# ---- main ---------------------------------------------------------------------------
def main() -> None:
    root, output_dir = Path(sys.argv[1]), Path(sys.argv[2])
    runs_root = root / "experiments" / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    sum_only, fedavg_rows, robust_rows = [], [], []
    for run_dir in sorted(runs_root.glob("*/*")):
        metadata_path = run_dir / "run_metadata.json"
        if not (run_dir / "instrumentation.npz").exists() or not metadata_path.exists():
            continue
        if json.loads(metadata_path.read_text(encoding="utf-8")).get("status") not in ("completed", "aborted"):
            continue
        config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
        run_kind = classify_run(config)
        if run_kind == "spdz2k_sum_only":
            sum_only += round_checks(run_dir, run_kind)
        elif run_kind == "fedavg" and run_dir.parent.name == "e1":
            fedavg_rows += round_checks(run_dir, run_kind)
        elif run_kind in ("spdz2k_robust", "plaintext_robust"):
            robust_rows += robust_checks(run_dir, run_kind)
    sum_only_frame, fedavg_frame = pd.DataFrame(sum_only), pd.DataFrame(fedavg_rows)
    sum_only_frame.to_csv(output_dir / "sum_only_round_exactness.csv", index=False)
    fedavg_frame.to_csv(output_dir / "fedavg_round_exactness.csv", index=False)
    robust_frame = pd.DataFrame(robust_rows)
    robust_frame.to_csv(output_dir / "robust_round_exactness.csv", index=False)

    pairs = []
    for run_dir in sorted((runs_root / "e1").glob("e1__smpc_only__*")):
        partner = runs_root / "e1" / run_dir.name.replace("__smpc_only__", "__baseline__")
        if (run_dir / "instrumentation.npz").exists() and (partner / "instrumentation.npz").exists():
            pairs += pair_rows(run_dir, partner, "spdz2k", "fedavg", 1_000_000)
    pair_frame = pd.DataFrame(pairs)
    pair_frame.to_csv(output_dir / "pair_divergence.csv", index=False)

    replay_frame = pd.DataFrame(replay_rows(output_dir, runs_root)) if (output_dir / "replays").exists() else None
    if replay_frame is not None:
        replay_frame.to_csv(output_dir / "replay_comparison.csv", index=False)

    lines = summarize(sum_only_frame, fedavg_frame, pair_frame, replay_frame)
    if len(robust_frame):
        lines += ["", "5. Robust program, per round: recorded model vs exact plaintext replication"
                      " (robust_reference -> decode -> apply_delta):"]
        for run_kind, group in robust_frame.groupby("kind"):
            checked = group.dropna(subset=["applied_vs_reference_mismatches"])
            lines.append(
                f"   {run_kind}: identical in {int((checked.applied_vs_reference_mismatches == 0).sum())} of "
                f"{len(checked)} rounds ({checked.run_id.nunique()} runs; rounds with an applied update: "
                f"{int(checked.update_applied.sum())}); mismatching coordinates in total "
                f"{int(checked.applied_vs_reference_mismatches.sum())}, max distance "
                f"{int(checked.applied_vs_reference_max_ulps.max())} ulps; rounds without entries: "
                f"{len(group) - len(checked)}")
    (output_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def summarize(sum_only, fedavg_frame, pairs, replays) -> list[str]:
    lines = ["Sum-only SPDZ2k vs plaintext FedAvg: diagnostic summary", ""]
    valid = sum_only.dropna(subset=["applied_vs_fixed_point_mismatches"])
    lines += [
        f"1. Sum-only SPDZ2k rounds checked: {len(valid)} rounds in {valid.run_id.nunique()} runs "
        f"(rounds without the cohort's entries: {len(sum_only) - len(valid)}).",
        f"   Inputs reconstructed exactly in float32: {int(valid.inputs_reconstructed_exactly.sum())} of {len(valid)} rounds.",
        f"   Applied model == exact fixed-point emulation (all {int(valid.coordinates.max())} coordinates): "
        f"{int((valid.applied_vs_fixed_point_mismatches == 0).sum())} of {len(valid)} rounds; "
        f"total mismatching coordinates {int(valid.applied_vs_fixed_point_mismatches.sum())}.",
        f"   Applied model vs FedAvg arithmetic on the same inputs: differs in "
        f"{int((valid.applied_vs_fedavg_mismatches > 0).sum())} of {len(valid)} rounds; mismatching coordinates per round "
        f"min {int(valid.applied_vs_fedavg_mismatches.min())}, median {float(valid.applied_vs_fedavg_mismatches.median()):.0f}, "
        f"max {int(valid.applied_vs_fedavg_mismatches.max())} (of {int(valid.coordinates.max())}); "
        f"max distance {int(valid.applied_vs_fedavg_max_ulps.max())} float32 ulps.",
        f"   Before the float32 cast, max |fixed point - FedAvg| = {valid.precast_max_abs_fixed_point_minus_fedavg.max():.3g} "
        f"(quantization bound K/(2 S N) per round: {valid.quantization_bound.min():.3g}..{valid.quantization_bound.max():.3g}).",
    ]
    totals: dict[str, list[int]] = {}
    for text in valid.fedavg_mismatches_by_magnitude:
        for label, (mismatched, total) in json.loads(text).items():
            entry = totals.setdefault(label, [0, 0])
            entry[0] += mismatched
            entry[1] += total
    lines.append("   Share of coordinates differing from FedAvg, by |parameter|: " + "; ".join(
        f"{label}: {m}/{t} ({(m / t if t else 0):.1%})" for label, (m, t) in totals.items()))
    tie_total = int(valid.fedavg_value_at_float32_tie.sum())
    at_tie = int(valid.applied_vs_fedavg_mismatches_at_tie.sum())
    off_tie = int(valid.applied_vs_fedavg_mismatches_off_tie.sum())
    lines.append(
        f"   FedAvg value exactly halfway between two float32 values (rounded half to even): {tie_total} "
        f"coordinate-rounds; the SPDZ2k output differs from FedAvg at {at_tie} of them, and at {off_tie} "
        f"other coordinate-rounds ({at_tie / max(at_tie + off_tie, 1):.1%} of all differences are at ties).")
    refused = valid[valid.encoded_peak_abs >= valid.ring_limit]
    lines.append(f"   Rounds whose inputs exceed the encoder's ring guard: {len(refused)}.")
    if len(fedavg_frame):
        fv = fedavg_frame.dropna(subset=["applied_vs_fedavg_mismatches"])
        lines += ["", f"2. Plaintext FedAvg rounds (E1) checked: {len(fv)} rounds in {fv.run_id.nunique()} runs.",
                  f"   Applied model == FedAvg emulation: {int((fv.applied_vs_fedavg_mismatches == 0).sum())} of {len(fv)} rounds "
                  f"(order search needed in {int((fv.fedavg_order != 'cohort order').sum())}).",
                  f"   Applied model vs fixed-point arithmetic on the same inputs: differs in "
                  f"{int((fv.applied_vs_fixed_point_mismatches > 0).sum())} of {len(fv)} rounds."]
    if len(pairs):
        lines += ["", "3. E1 pairs smpc_only / baseline (same attack and seed):"]
        for (run_a, run_b), group in pairs.groupby(["run_spdz2k", "run_fedavg"], sort=True):
            group = group.sort_values("round")
            first = group[group.global_mismatched_coordinates > 0]["round"]
            r1 = group[group["round"] == 1]
            r1_text = ""
            if len(r1):
                r1 = r1.iloc[0]
                r1_text = (f"round 1: inputs equal={bool(r1.inputs_equal)}, previous equal={bool(r1.previous_global_equal)}, "
                           f"SPDZ2k==fixed-point {r1.get('spdz2k_equals_fixed_point')}, FedAvg==fedavg {r1.get('fedavg_equals_fedavg')}, "
                           f"{int(r1.global_mismatched_coordinates)} coordinates differ (max {r1.global_max_abs_difference:.2g})")
            growth = ", ".join(f"{value:.1e}" for value in group.global_l2_difference)
            accuracy = group["global_accuracy_difference"].abs().max() if "global_accuracy_difference" in group else float("nan")
            lines.append(f"   {run_a.replace('e1__smpc_only__', '')}: first differing global model in round "
                         f"{int(first.iloc[0]) if len(first) else '-'}; {r1_text}; "
                         f"L2 distance by round [{growth}]; max |accuracy difference| {accuracy:.4f}")
    if replays is not None and len(replays):
        lines += ["", "4. Plaintext replays with the sum-only arithmetic:"]
        for _, row in replays.iterrows():
            if "compared_with" not in row or pd.isna(row.get("compared_with")):
                lines.append(f"   {row['replay']}: status {row.get('status')}")
                continue
            lines.append(f"   {row['replay']} (S={row['scale']}) vs {row['compared_with']} {row['target_run']}: "
                         f"identical global model in {row['rounds_with_identical_global_model']}/{row['rounds']} rounds, "
                         f"metrics identical in all rounds: {row['metrics_identical_in_all_rounds']}, "
                         f"max |accuracy difference| {row['max_abs_accuracy_difference']}")
    return lines


if __name__ == "__main__":
    main()
