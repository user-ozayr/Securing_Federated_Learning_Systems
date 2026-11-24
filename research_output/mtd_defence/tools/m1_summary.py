"""Summary tables for the direction-screen studies (M1, M2).

    python research_output/mtd_defence/tools/m1_summary.py research_output/mtd_defence/experiments [m1|m2]

Per (condition, attack): accuracy (mean of the last three rounds), final ASR,
direction-screen and overall rejection rates for malicious and honest
participations; mean over seeds with the per-seed values.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CONDITION_ORDER = ["reference_defence", "reference_direction_all", "reference_direction_public",
                   "reference_direction_secret", "reference_direction_secret_t52",
                   "reference_defence_mtd", "reference_direction_secret_mtd",
                   "reference_direction_all_t52", "reference_direction_public_t52",
                   "reference_direction_secret10_t52", "reference_direction_secret_mtd_t52", "smpc_direction_mtd"]
ATTACK_ORDER = ["none", "label_flip", "backdoor", "adaptive_backdoor", "evasive_backdoor",
                "adaptive_backdoor__jit4"]


def _ids(value) -> set[int]:
    try:
        return set(int(v) for v in json.loads(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()


def run_record(run_dir: Path) -> dict | None:
    meta = json.loads((run_dir / "run_metadata.json").read_text())
    results = next(run_dir.glob("*_results.csv"), None)
    if results is None or meta.get("status") not in ("completed", "aborted"):
        return None
    frame = pd.read_csv(results)
    parts = run_dir.name.split("__")
    condition, attack, seed = parts[1], "__".join(parts[2:-1]), parts[-1]
    last = frame.sort_values("round").tail(3)
    record = {"condition": condition, "attack": attack, "seed": int(seed[1:]),
              "status": meta.get("status"), "rounds": int(frame["round"].max()),
              "accuracy": float(last["global_accuracy"].mean()),
              "asr": float(frame.sort_values("round")["backdoor_asr"].iloc[-1])
              if "backdoor_asr" in frame else np.nan}
    mal_part = hon_part = dir_tp = dir_fp = rej_tp = rej_fp = 0
    for _, row in frame.iterrows():
        selected = _ids(row.get("selected_client_ids"))
        malicious = _ids(row.get("malicious_client_ids")) & selected
        honest = selected - malicious
        rejected = _ids(row.get("defence_rejected_client_ids"))
        direction = _ids(row.get("direction_rejected_client_ids"))
        mal_part += len(malicious)
        hon_part += len(honest)
        dir_tp += len(direction & malicious)
        dir_fp += len(direction & honest)
        rej_tp += len(rejected & malicious)
        rej_fp += len(rejected & honest)
    record.update({
        "malicious_participations": mal_part,
        "direction_tpr": dir_tp / mal_part if mal_part else np.nan,
        "direction_fpr": dir_fp / hon_part if hon_part else np.nan,
        "rejection_tpr": rej_tp / mal_part if mal_part else np.nan,
        "rejection_fpr": rej_fp / hon_part if hon_part else np.nan,
    })
    return record


def main() -> None:
    root = Path(sys.argv[1])
    study = sys.argv[2] if len(sys.argv) > 2 else "m1"
    records = [r for d in sorted((root / "runs" / study).glob(f"{study}__*"))
               if (r := run_record(d))]
    frame = pd.DataFrame(records)
    frame.to_csv(root / f"{study}_runs.csv", index=False)
    metrics = ["accuracy", "asr", "direction_tpr", "direction_fpr", "rejection_tpr", "rejection_fpr"]
    summary = frame.groupby(["condition", "attack"])[metrics].agg(["mean", "min", "max"])
    summary.columns = [f"{m}_{s}" for m, s in summary.columns]
    summary = summary.reset_index()
    summary["seeds"] = frame.groupby(["condition", "attack"]).size().values
    summary["condition"] = pd.Categorical(summary["condition"], CONDITION_ORDER, ordered=True)
    summary["attack"] = pd.Categorical(summary["attack"], ATTACK_ORDER, ordered=True)
    summary = summary.sort_values(["attack", "condition"])
    summary.to_csv(root / f"{study}_summary.csv", index=False)
    pd.set_option("display.width", 220)
    cols = ["attack", "condition", "seeds", "accuracy_mean", "asr_mean", "asr_min", "asr_max",
            "direction_tpr_mean", "direction_fpr_mean", "rejection_tpr_mean", "rejection_fpr_mean"]
    print(summary[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
