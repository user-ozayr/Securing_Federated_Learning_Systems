"""Aggregate completed runs into metric tables, summaries and figures.

Inputs: ``<root>/runs/<study>/<run_id>/`` with ``*_results.csv`` (per round),
``round_analysis.csv`` (influence/correctness) and ``run_metadata.json``.

Outputs (all CSV/JSON are machine-readable; nothing is estimated here):

* ``metrics/all_rounds.csv`` and ``metrics/final_round.csv``
* ``metrics/run_index.csv`` (status, timing, commitment hashes of every run)
* ``summaries/summary_by_condition.csv`` – mean, std and 95% t-interval per
  study/condition/attack over seeds
* ``summaries/paired_differences.csv`` – per-seed differences against the
  baseline condition under the same attack
* ``summaries/accuracy_over_rounds.csv`` – per-round mean/CI curves
* ``figures/*.png``
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fl_security.evaluation.csv_safety import sanitize_csv_dataframe
from fl_security.evaluation.statistics import summarize_values


def _read_runs(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rounds, index = [], []
    for meta_path in sorted((root / "runs").glob("*/*/run_metadata.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        run_dir = meta_path.parent
        entry = {k: meta.get(k) for k in (
            "run_id", "study", "condition", "attack", "seed", "uses_mpc", "mtd_schedule",
            "status", "detail", "wall_seconds", "git_commit", "git_dirty", "config_sha256",
            "mtd_secret_sha256_commitment", "started_utc", "finished_utc")}
        entry.update({f"analysis_{k}": v for k, v in (meta.get("analysis") or {}).items()})
        index.append(entry)
        if meta.get("status") not in ("completed", "aborted"):
            continue
        results = next(run_dir.glob("*_results.csv"), None)
        if results is None:
            continue
        frame = pd.read_csv(results)
        frame = frame[frame["round"] > 0].copy()
        if frame.empty:
            continue
        analysis = run_dir / "round_analysis.csv"
        if analysis.exists():
            frame = frame.merge(pd.read_csv(analysis), on="round", how="left", suffixes=("", "_analysis"))
        for key in ("run_id", "study", "condition", "attack", "seed", "uses_mpc", "mtd_schedule"):
            frame[key] = meta.get(key)
        frame["run_status"] = meta.get("status")
        rounds.append(frame)
    all_rounds = pd.concat(rounds, ignore_index=True) if rounds else pd.DataFrame()
    return all_rounds, pd.DataFrame(index)


def _detection(group: pd.DataFrame) -> dict:
    out = {}
    if "rejected_true_positives" not in group or group["rejected_true_positives"].isna().all():
        return out
    malicious = group["malicious_selected"].sum()
    honest = group["honest_participants"].sum()
    out["rejection_tpr"] = group["rejected_true_positives"].sum() / malicious if malicious else np.nan
    out["rejection_fpr"] = group["rejected_false_positives"].sum() / honest if honest else np.nan
    out["flag_tpr"] = group["flagged_true_positives"].sum() / malicious if malicious else np.nan
    out["flag_fpr"] = group["flagged_false_positives"].sum() / honest if honest else np.nan
    out["output_check_failures"] = int((group["defence_output_check_passed"] == 0).sum())
    return out


def per_run_summary(all_rounds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for run_id, group in all_rounds.groupby("run_id"):
        group = group.sort_values("round")
        last = group.iloc[-1]
        row = {k: last[k] for k in ("run_id", "study", "condition", "attack", "seed", "uses_mpc", "mtd_schedule")}
        row["run_status"] = last.get("run_status", "completed")
        row["rounds_completed"] = int(group["round"].max())
        row["aborted"] = int(row["run_status"] == "aborted")
        # For aborted runs, "final" refers to the last completed round.
        row["final_accuracy"] = float(last["global_accuracy"])
        row["final_loss"] = float(last["global_loss"])
        row["last3_mean_accuracy"] = float(group["global_accuracy"].tail(3).mean())
        if "backdoor_asr" in group and group["backdoor_asr"].notna().any():
            row["final_backdoor_asr"] = float(last["backdoor_asr"])
            row["max_backdoor_asr"] = float(group["backdoor_asr"].max())
        row["mean_malicious_selected"] = float(group["malicious_selected"].mean())
        row["mean_round_seconds"] = float(group["round_seconds"].mean())
        for column in ("mpc_protocol_seconds_max", "mpc_global_data_sent_mb", "mp_spdz_input_bytes",
                       "mpc_start_seconds", "mpc_receive_seconds", "aggregation_seconds"):
            if column in group and group[column].notna().any():
                row[f"mean_{column}"] = float(group[column].mean())
        for column in ("malicious_share_effective", "malicious_share_submitted",
                       "deviation_from_honest_relative", "cosine_with_honest"):
            if column in group and group[column].notna().any():
                row[f"mean_{column}"] = float(group[column].mean())
        if "reference_max_abs_error" in group and group["reference_max_abs_error"].notna().any():
            row["max_reference_abs_error"] = float(group["reference_max_abs_error"].max())
        if "reference_relative_error" in group and group["reference_relative_error"].notna().any():
            row["max_reference_relative_error"] = float(group["reference_relative_error"].max())
            row["max_global_abs"] = float(group["global_max_abs"].max())
        row.update(_detection(group))
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(final: pd.DataFrame) -> pd.DataFrame:
    metrics = [c for c in final.columns if c not in
               {"run_id", "study", "condition", "attack", "seed", "uses_mpc", "mtd_schedule", "run_status"}]
    rows = []
    for (study, condition, attack), group in final.groupby(["study", "condition", "attack"]):
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            rows.append({"study": study, "condition": condition, "attack": attack, "metric": metric,
                         "seeds": ",".join(str(s) for s in sorted(group["seed"])),
                         **summarize_values(values.tolist())})
    return pd.DataFrame(rows)


def paired(final: pd.DataFrame, baseline: str = "baseline") -> pd.DataFrame:
    rows = []
    metrics = ["final_accuracy", "last3_mean_accuracy", "final_backdoor_asr"]
    for (study, attack), group in final.groupby(["study", "attack"]):
        base = group[group["condition"] == baseline].set_index("seed")
        if base.empty:
            continue
        for condition, other in group[group["condition"] != baseline].groupby("condition"):
            other = other.set_index("seed")
            seeds = sorted(set(base.index) & set(other.index))
            for metric in metrics:
                if metric not in other or metric not in base:
                    continue
                diffs = [float(other.loc[s, metric] - base.loc[s, metric]) for s in seeds
                         if pd.notna(other.loc[s, metric]) and pd.notna(base.loc[s, metric])]
                if diffs:
                    rows.append({"study": study, "attack": attack, "baseline": baseline,
                                 "condition": condition, "metric": metric,
                                 "paired_seeds": len(diffs), **summarize_values(diffs)})
    return pd.DataFrame(rows)


def curves(all_rounds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (study, condition, attack, round_num), group in all_rounds.groupby(
            ["study", "condition", "attack", "round"]):
        for metric in ("global_accuracy", "global_loss", "backdoor_asr"):
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if len(values):
                rows.append({"study": study, "condition": condition, "attack": attack,
                             "round": int(round_num), "metric": metric, **summarize_values(values.tolist())})
    return pd.DataFrame(rows)


def figures(curve_table: pd.DataFrame, out: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for (study, attack), group in curve_table.groupby(["study", "attack"]):
        for metric, label in (("global_accuracy", "clean test accuracy"), ("backdoor_asr", "backdoor ASR")):
            data = group[group["metric"] == metric]
            if data.empty or (metric == "backdoor_asr" and attack not in ("backdoor", "adaptive_backdoor")):
                continue
            figure, axis = plt.subplots(figsize=(7, 4.2))
            for condition, series in data.groupby("condition"):
                series = series.sort_values("round")
                axis.plot(series["round"], series["mean"], marker="o", markersize=3, label=condition)
                if series["n"].max() > 1:
                    axis.fill_between(series["round"], series["ci95_lower"], series["ci95_upper"], alpha=0.12)
            axis.set_xlabel("round")
            axis.set_ylabel(label)
            axis.set_title(f"{study}: {attack} – {label} (mean, 95% CI over seeds)")
            axis.grid(alpha=0.3)
            axis.legend(fontsize=7, ncol=2)
            figure.tight_layout()
            path = out / f"{study}_{attack}_{metric}.png"
            figure.savefig(path, dpi=130)
            plt.close(figure)
            written.append(path.name)
    return written


MATRIX_CRITERIA = (
    "Verdicts (per study/attack/condition, means over seeds): 'no attack effect' if the attack "
    "lowers FedAvg baseline accuracy by < 0.02 and (backdoor) baseline ASR < 0.10; otherwise "
    "'mitigated' if the condition's accuracy is within 0.02 of its own no-attack accuracy and "
    "(backdoor) its ASR < 0.10; 'partially mitigated' if it recovers >= 50 % of the baseline's "
    "accuracy loss, or (backdoor) halves the baseline ASR without losing more accuracy than the "
    "undefended baseline under the same attack; else 'not mitigated'. A destroyed model also has a "
    "low ASR, so a low ASR alone never counts; rows with last-3 accuracy < 0.2 are marked "
    "model_destroyed and their ASR is not meaningful. References come from the same study; a study "
    "without a run of its own uses the study that shares its setting (e1x, e2, e4 -> e1, then e1x; "
    "reference_defence -> smpc_defence, the same algorithm executed in SPDZ2k; '<attack>__default' "
    "-> '<attack>'), always over the same seeds. The *_reference columns name the runs used."
)

# Studies whose settings equal another study's except for the factor they vary.
REFERENCE_FALLBACKS = {"e1x": ("e1",), "e2": ("e1", "e1x"), "e4": ("e1", "e1x")}
# The plaintext execution of the robust algorithm and its SPDZ2k execution are
# trajectory-identical (equivalence_checks.csv), so one can stand in for the other.
CONDITION_ALIASES = {"reference_defence": "smpc_defence"}
DESTROYED_ACCURACY = 0.2


def _find_reference(final: pd.DataFrame, study: str, condition: str, attacks: list[str],
                    seeds: list) -> tuple[pd.DataFrame | None, str | None]:
    """First available (study, condition, attack) runs over the given seeds."""
    conditions = [condition] + ([CONDITION_ALIASES[condition]] if condition in CONDITION_ALIASES else [])
    for candidate_study in (study, *REFERENCE_FALLBACKS.get(study, ())):
        for candidate_condition in conditions:
            for candidate_attack in attacks:
                group = final[(final.study == candidate_study) & (final.condition == candidate_condition)
                              & (final.attack == candidate_attack) & final.seed.isin(seeds)]
                if len(group):
                    used = ",".join(str(seed) for seed in sorted(group.seed))
                    return group, f"{candidate_study}/{candidate_condition}/{candidate_attack} (seeds {used})"
    return None, None


def matrix(final: pd.DataFrame) -> pd.DataFrame:
    """Attack/defence matrix with explicit, mechanical verdict criteria."""
    rows = []
    for (study, condition, attack), group in final.groupby(["study", "condition", "attack"]):
        values = group.mean(numeric_only=True)
        seeds = sorted(group["seed"])
        row = {"study": study, "condition": condition, "attack": attack, "seeds": int(len(group))}
        for column in ("final_accuracy", "last3_mean_accuracy", "final_backdoor_asr",
                       "mean_malicious_share_submitted", "mean_malicious_share_effective",
                       "mean_deviation_from_honest_relative", "rejection_tpr", "rejection_fpr",
                       "flag_tpr", "flag_fpr", "output_check_failures", "mean_round_seconds",
                       "mean_mpc_protocol_seconds_max", "mean_mpc_global_data_sent_mb",
                       "max_reference_abs_error"):
            if column in values and pd.notna(values[column]):
                row[column] = float(values[column])
        accuracy = row.get("last3_mean_accuracy")
        row["model_destroyed"] = int(accuracy is not None and accuracy < DESTROYED_ACCURACY)
        is_clean = attack == "none" or attack.startswith("none__")
        suffix = attack.split("__", 1)[1] if "__" in attack else None
        clean_attacks = ([f"none__{suffix}"] if suffix else []) + ["none"]
        # '<attack>__default' is the unmodified attack of the study sharing the setting
        attack_names = [attack] + ([attack.split("__", 1)[0]] if suffix == "default" else [])
        verdict = "not applicable" if is_clean else "insufficient reference"
        if not is_clean:
            clean, clean_label = _find_reference(final, study, condition, clean_attacks, seeds)
            if clean is not None and accuracy is not None:
                row["degradation_vs_own_clean"] = float(clean["last3_mean_accuracy"].mean() - accuracy)
                row["clean_reference"] = clean_label
            base_attack, base_attack_label = _find_reference(final, study, "baseline", attack_names, seeds)
            base_clean, base_clean_label = _find_reference(final, study, "baseline", clean_attacks, seeds)
            if base_attack is not None and base_clean is not None and accuracy is not None:
                row["baseline_reference"] = base_attack_label
                row["baseline_clean_reference"] = base_clean_label
                base_accuracy = float(base_attack["last3_mean_accuracy"].mean())
                baseline_loss = float(base_clean["last3_mean_accuracy"].mean()) - base_accuracy
                row["baseline_accuracy_loss"] = baseline_loss
                asr = row.get("final_backdoor_asr")
                base_asr = (float(base_attack["final_backdoor_asr"].mean())
                            if "final_backdoor_asr" in base_attack and base_attack["final_backdoor_asr"].notna().any()
                            else np.nan)
                is_backdoor = "backdoor" in attack
                effective = baseline_loss >= 0.02 or (is_backdoor and pd.notna(base_asr) and base_asr >= 0.10)
                if not effective:
                    verdict = "no attack effect"
                else:
                    own_loss = row.get("degradation_vs_own_clean", np.inf)
                    asr_ok = (not is_backdoor) or (asr is not None and asr < 0.10)
                    recovered = (accuracy - base_accuracy) / baseline_loss if baseline_loss >= 0.02 else np.nan
                    not_worse = accuracy >= base_accuracy - 0.02
                    halved = (is_backdoor and asr is not None and pd.notna(base_asr)
                              and asr <= base_asr / 2 and not_worse)
                    if own_loss < 0.02 and asr_ok:
                        verdict = "mitigated"
                    elif (pd.notna(recovered) and recovered >= 0.5) or halved:
                        verdict = "partially mitigated"
                    else:
                        verdict = "not mitigated"
                    if pd.notna(recovered):
                        row["recovered_fraction_of_baseline_loss"] = float(recovered)
        row["verdict"] = verdict if condition != "baseline" or is_clean else (
            "reference (undefended)" if verdict != "no attack effect" else verdict)
        rows.append(row)
    return pd.DataFrame(rows)


def benchmark_report(benchmark_dir: Path) -> pd.DataFrame | None:
    path = benchmark_dir / "benchmark_results.jsonl"
    if not path.exists():
        return None
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    raw = pd.DataFrame(records)
    sanitize_csv_dataframe(raw).to_csv(benchmark_dir / "benchmark_results.csv", index=False)
    raw["variant"] = np.where(raw["program"] == "weighted_sum", "sum_only",
                              raw["mode"].astype(str) + "_" + raw["threshold"].astype(str))
    rows = []
    for (variant, dimension, parties), group in raw.groupby(["variant", "dimension", "parties"]):
        done = group[group["status"] == "completed"]
        row = {"variant": variant, "dimension": int(dimension), "parties": int(parties),
               "attempts": int(len(group)), "completed": int(len(done)),
               "statuses": ",".join(sorted(group["status"].astype(str)))}
        for metric in ("total_seconds", "start_seconds", "client_input_seconds_total", "output_seconds",
                       "protocol_seconds_max", "global_data_sent_mb", "peak_party_rss_mib"):
            if metric in done and done[metric].notna().any():
                stats = summarize_values(done[metric].dropna().tolist())
                row[f"{metric}_mean"] = stats["mean"]
                row[f"{metric}_std"] = stats["std"]
        for metric in ("integer_triples", "integer_bits", "integer_opens", "vm_rounds", "compile_seconds"):
            if metric in group:
                row[metric] = float(group[metric].max())
        if "bit_exact_vs_reference" in done:
            row["bit_exact_all"] = bool(done["bit_exact_vs_reference"].fillna(True).all())
        if "max_abs_error" in done and done["max_abs_error"].notna().any():
            row["max_abs_error"] = float(done["max_abs_error"].max())
        rows.append(row)
    summary = pd.DataFrame(rows).sort_values(["parties", "variant", "dimension"])
    sanitize_csv_dataframe(summary).to_csv(benchmark_dir / "benchmark_summary.csv", index=False)
    return summary


def _cell(stats: dict | None, digits: int = 3) -> str:
    if not stats or stats.get("n", 0) == 0 or pd.isna(stats.get("mean")):
        return "–"
    text = f"{stats['mean']:.{digits}f}"
    if stats.get("n", 0) > 1 and pd.notna(stats.get("ci95_lower")):
        half = (stats["ci95_upper"] - stats["ci95_lower"]) / 2
        text += f" ± {half:.{digits}f}"
    return text + f" (n={int(stats['n'])})"


def key_tables(final: pd.DataFrame) -> str:
    """Markdown tables generated directly from per-run results (mean ± 95 % CI half-width)."""
    lines = ["# Key results (generated by fl_security.experiments.report)", "",
             "Values: mean ± half-width of the two-sided 95 % Student-t interval over seeds (n = seeds).", ""]

    def append_metric_table(
        study: str,
        metric: str,
        conditions: list[str],
        attacks: list[str],
        title: str,
        digits: int = 3,
        frame: pd.DataFrame | None = None,
    ) -> None:
        source = final if frame is None else frame
        subset = source[source["study"] == study]
        if subset.empty or metric not in subset:
            return
        lines.extend([f"## {title}", "", "| condition | " + " | ".join(attacks) + " |",
                      "|---|" + "---|" * len(attacks)])
        for condition in conditions:
            cells = []
            for attack in attacks:
                values = pd.to_numeric(subset[(subset.condition == condition) & (subset.attack == attack)][metric],
                                       errors="coerce").dropna()
                cells.append(_cell(summarize_values(values.tolist()) if len(values) else None, digits))
            if any(cell != "–" for cell in cells):
                lines.append(f"| {condition} | " + " | ".join(cells) + " |")
        lines.append("")

    core = ["baseline", "mtd_only", "smpc_only", "smpc_mtd", "smpc_clip", "smpc_defence_mtd"]
    attacks = ["none", "label_flip", "sign_flip", "scaled_replacement", "random_noise", "backdoor"]

    append_metric_table(
        "e1", "last3_mean_accuracy", core, attacks,
        "E1 : clean accuracy (mean of last 3 rounds)",
    )
    append_metric_table(
        "e1", "final_backdoor_asr", core, ["none", "backdoor"],
        "E1 : backdoor ASR at the final round",
    )
    append_metric_table(
        "e1", "mean_malicious_share_effective", core, attacks[1:],
        "E1 : malicious share of the applied aggregate (after defence)",
    )
    append_metric_table(
        "e1", "mean_malicious_share_submitted", core, attacks[1:],
        "E1 : malicious share of the submitted updates (before defence)",
    )
    append_metric_table(
        "e1", "rejection_tpr", ["smpc_defence_mtd"], attacks[1:],
        "E1 : rejection true-positive rate",
    )
    append_metric_table(
        "e1", "rejection_fpr", ["smpc_defence_mtd"], attacks,
        "E1 : rejection false-positive rate (honest)",
    )
    append_metric_table(
        "e1", "mean_deviation_from_honest_relative", core, attacks,
        "E1 : relative deviation of the applied update from honest-only FedAvg",
    )
    append_metric_table(
        "e1", "mean_round_seconds", core, ["none"],
        "E1 : mean round wall time (s)", 1,
    )
    append_metric_table(
        "e1", "mean_mpc_protocol_seconds_max", core, ["none"],
        "E1 : MP-SPDZ protocol time per round (s)", 1,
    )
    append_metric_table(
        "e1", "mean_mpc_global_data_sent_mb", core, ["none"],
        "E1 : MP-SPDZ global traffic per round (MB)", 0,
    )

    extended = ["baseline", "plaintext_robust", "smpc_screen", "smpc_defence", "smpc_defence_mtd"]
    merged = pd.concat([
        final[final.study == "e1x"],
        final[(final.study == "e1") & final.condition.isin(["baseline", "smpc_defence_mtd"])],
    ]).assign(study="e1x")
    append_metric_table(
        "e1x", "last3_mean_accuracy", extended,
        ["none", "sign_flip", "scaled_replacement", "backdoor"],
        "E1x : clean accuracy, extended defences (baseline and full framework from E1)",
        frame=merged,
    )
    append_metric_table(
        "e1x", "final_backdoor_asr", extended, ["backdoor"],
        "E1x : backdoor ASR, extended defences",
        frame=merged,
    )
    append_metric_table(
        "e2", "final_backdoor_asr",
        ["baseline", "plaintext_robust", "smpc_clip", "smpc_defence_mtd"],
        ["adaptive_backdoor"],
        "E2 : adaptive (constrain-and-scale) backdoor: ASR",
    )
    append_metric_table(
        "e2", "last3_mean_accuracy",
        ["baseline", "plaintext_robust", "smpc_clip", "smpc_defence_mtd"],
        ["adaptive_backdoor"],
        "E2 : adaptive backdoor: clean accuracy",
    )
    e3 = final[final.study == "e3"]
    if not e3.empty:
        lines.extend(["## E3 – schedule predictability (FedAvg, backdoor, budget 2)", "",
                      "| schedule / adversary | final ASR | mean malicious per round | clean accuracy |",
                      "|---|---|---|---|"])
        for attack in sorted(e3.attack.unique()):
            group = e3[e3.attack == attack]
            label = attack.replace("backdoor__", "")
            lines.append(f"| {label} | {_cell(summarize_values(group['final_backdoor_asr'].dropna().tolist()))} | "
                         f"{_cell(summarize_values(group['mean_malicious_selected'].dropna().tolist()), 2)} | "
                         f"{_cell(summarize_values(group['last3_mean_accuracy'].dropna().tolist()))} |")
        lines.append("")
    e4 = final[final.study == "e4"]
    if not e4.empty:
        lines.extend(["## E4 – sweeps (FedAvg vs plaintext reference of the adaptive defence)", "",
                      "| attack setting | condition | final ASR | clean accuracy |", "|---|---|---|---|"])
        for (attack, condition), group in e4.groupby(["attack", "condition"]):
            lines.append(f"| {attack} | {condition} | "
                         f"{_cell(summarize_values(group['final_backdoor_asr'].dropna().tolist()))} | "
                         f"{_cell(summarize_values(group['last3_mean_accuracy'].dropna().tolist()))} |")
        lines.append("")
    e5 = final[final.study == "e5"]
    if not e5.empty:
        lines.extend(["## E5 – non-IID (Dirichlet 0.5)", "", "| condition | attack | clean accuracy | final ASR |",
                      "|---|---|---|---|"])
        for (condition, attack), group in e5.groupby(["condition", "attack"]):
            lines.append(f"| {condition} | {attack} | "
                         f"{_cell(summarize_values(group['last3_mean_accuracy'].dropna().tolist()))} | "
                         f"{_cell(summarize_values(group['final_backdoor_asr'].dropna().tolist()))} |")
        lines.append("")
    return "\n".join(lines)


EQUIVALENCE_PAIRS = (
    # (label, run A pattern, run B pattern, expectation)
    ("SPDZ2k robust vs plaintext reference of the same algorithm",
     "e1x__smpc_defence__backdoor__s{seed}", "e4__reference_defence__backdoor__default__s{seed}",
     "identical up to float32 model arithmetic"),
    ("SPDZ2k sum-only vs plaintext FedAvg (static participation)",
     "e1__smpc_only__{attack}__s{seed}", "e1__baseline__{attack}__s{seed}",
     "identical up to fixed-point rounding (scale 1e6)"),
    ("Determinism: adaptive attacker without a published threshold vs boosted backdoor (FedAvg)",
     "e2__baseline__adaptive_backdoor__s{seed}", "e1__baseline__backdoor__s{seed}",
     "identical (same update scaling)"),
)


def equivalence(all_rounds: pd.DataFrame) -> pd.DataFrame:
    """Per-round comparison of runs that should produce the same model trajectory."""
    rows = []
    by_run = {run_id: group.sort_values("round") for run_id, group in all_rounds.groupby("run_id")}
    seeds = sorted({int(s) for s in all_rounds["seed"].dropna().unique()})
    attacks = sorted(all_rounds["attack"].dropna().unique())
    for label, pattern_a, pattern_b, expectation in EQUIVALENCE_PAIRS:
        for seed in seeds:
            for attack in (attacks if "{attack}" in pattern_a else [None]):
                run_a = pattern_a.format(seed=seed, attack=attack)
                run_b = pattern_b.format(seed=seed, attack=attack)
                if run_a not in by_run or run_b not in by_run:
                    continue
                a, b = by_run[run_a], by_run[run_b]
                merged = a.merge(b, on="round", suffixes=("_a", "_b"))
                if merged.empty:
                    continue
                row = {"comparison": label, "run_a": run_a, "run_b": run_b, "expectation": expectation,
                       "rounds": int(len(merged)),
                       "max_abs_accuracy_difference": float((merged["global_accuracy_a"] - merged["global_accuracy_b"]).abs().max()),
                       "max_abs_loss_difference": float((merged["global_loss_a"] - merged["global_loss_b"]).abs().max())}
                if "backdoor_asr_a" in merged and merged["backdoor_asr_a"].notna().any():
                    row["max_abs_asr_difference"] = float(
                        (merged["backdoor_asr_a"] - merged["backdoor_asr_b"]).abs().max())
                rows.append(row)
    return pd.DataFrame(rows)


def build_manifest(completion_root: Path, output_name: str = "final_validation_manifest.json",
                   extra: dict | None = None) -> dict:
    """SHA-256 and size of every evidence file below ``completion_root``."""
    import hashlib

    files = []
    for path in sorted(completion_root.rglob("*")):
        if not path.is_file() or path.name == output_name:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        files.append({"path": path.relative_to(completion_root).as_posix(),
                      "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    manifest = {"root": str(completion_root), "file_count": len(files),
                "total_bytes": sum(item["bytes"] for item in files), **(extra or {}), "files": files}
    (completion_root / output_name).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {k: v for k, v in manifest.items() if k != "files"}


def build_reports(root: Path) -> dict:
    all_rounds, index = _read_runs(root)
    metrics_dir, summaries_dir = root / "metrics", root / "summaries"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    sanitize_csv_dataframe(index).to_csv(metrics_dir / "run_index.csv", index=False)
    if all_rounds.empty:
        return {"runs": len(index), "completed": 0}
    sanitize_csv_dataframe(all_rounds).to_csv(metrics_dir / "all_rounds.csv", index=False)
    final = per_run_summary(all_rounds)
    sanitize_csv_dataframe(final).to_csv(metrics_dir / "final_round.csv", index=False)
    summary = summarize(final)
    sanitize_csv_dataframe(summary).to_csv(summaries_dir / "summary_by_condition.csv", index=False)
    differences = paired(final)
    sanitize_csv_dataframe(differences).to_csv(summaries_dir / "paired_differences.csv", index=False)
    curve_table = curves(all_rounds)
    sanitize_csv_dataframe(curve_table).to_csv(summaries_dir / "accuracy_over_rounds.csv", index=False)
    written = figures(curve_table, root / "figures")
    attack_matrix = matrix(final)
    sanitize_csv_dataframe(attack_matrix).to_csv(summaries_dir / "attack_defence_matrix.csv", index=False)
    (summaries_dir / "key_results.md").write_text(key_tables(final), encoding="utf-8")
    sanitize_csv_dataframe(equivalence(all_rounds)).to_csv(summaries_dir / "equivalence_checks.csv", index=False)
    (summaries_dir / "attack_defence_matrix_criteria.txt").write_text(MATRIX_CRITERIA + "\n", encoding="utf-8")
    status_counts = index["status"].value_counts().to_dict() if not index.empty else {}
    result = {"runs": int(len(index)), "status_counts": status_counts,
              "completed_runs_with_rounds": int(final.shape[0]), "figures": len(written)}
    (summaries_dir / "report_status.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
