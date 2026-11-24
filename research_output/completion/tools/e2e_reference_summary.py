"""Summarize end-to-end checks of the applied aggregate across all runs.

Each instrumented run records a round_analysis.csv file. For every round, the
analysis recomputes the expected aggregate in float64 from the updates clients
submitted, using FedAvg, fixed-point FedAvg, or the exact integer robust
reference. This script groups the comparisons by aggregation path.

Usage: python e2e_reference_summary.py <experiments_root>
Writes <experiments_root>/summaries/end_to_end_reference_check.csv, with one
row per run, and prints a table for each path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

HEALTHY_MODEL_MAX_ABS = 100.0   # Parameter magnitudes above 100 indicate a diverged model.


def path_label(smpc: bool, kind: str) -> str:
    if kind == "robust_reference":
        return "SPDZ2k robust program" if smpc else "plaintext execution of the robust algorithm"
    if kind == "fedavg_fixed_point":
        return "SPDZ2k sum-only program"
    return "plaintext FedAvg"


def main() -> None:
    root = Path(sys.argv[1])
    records = []
    for analysis in sorted(root.glob("runs/*/*/round_analysis.csv")):
        run_dir = analysis.parent
        metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
        config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
        frame = pd.read_csv(analysis)
        smpc = bool((config.get("smpc") or {}).get("enabled"))
        if "reference_max_abs_error" not in frame or frame["reference_max_abs_error"].isna().all():
            records.append({"study": metadata["study"], "run_id": metadata["run_id"],
                            "status": metadata.get("status"), "path": "plaintext detector (no exact reference)",
                            "rounds_compared": 0})
            continue
        checked = frame[frame["reference_max_abs_error"].notna()]
        kinds = sorted(set(checked["reference_kind"].astype(str)))
        records.append({
            "study": metadata["study"], "run_id": metadata["run_id"], "status": metadata.get("status"),
            "path": path_label(smpc, kinds[0]) if len(kinds) == 1 else "mixed:" + ",".join(kinds),
            "rounds_compared": int(len(checked)),
            "max_abs_error": float(checked["reference_max_abs_error"].max()),
            "max_relative_error": float(checked["reference_relative_error"].max()),
            "max_model_abs": float(checked["global_max_abs"].max()),
        })
    table = pd.DataFrame(records)
    out = root / "summaries" / "end_to_end_reference_check.csv"
    table.to_csv(out, index=False)
    print(f"runs: {len(table)}  written: {out}")
    checked = table[table["rounds_compared"] > 0]
    for path, group in checked.groupby("path"):
        healthy = group[group["max_model_abs"] <= HEALTHY_MODEL_MAX_ABS]
        diverged = group[group["max_model_abs"] > HEALTHY_MODEL_MAX_ABS]
        print(f"\n{path}: runs={len(group)} rounds={int(group['rounds_compared'].sum())}")
        print(f"  max abs error, all runs            = {group['max_abs_error'].max():.3e}")
        print(f"  max abs error, healthy models      = {healthy['max_abs_error'].max() if len(healthy) else float('nan'):.3e}"
              f"  (runs {len(healthy)}; model |w| <= {HEALTHY_MODEL_MAX_ABS:g})")
        print(f"  median of per-run max abs error    = {group['max_abs_error'].median():.3e}")
        print(f"  max relative error (L2), all runs  = {group['max_relative_error'].max():.3e}")
        if len(diverged):
            print(f"  diverged models: {len(diverged)} runs, max |w| up to {diverged['max_model_abs'].max():.3e}: "
                  + ", ".join(diverged['run_id']))
    skipped = table[table["rounds_compared"] == 0]
    if len(skipped):
        print(f"\nwithout exact reference: {len(skipped)} runs ({', '.join(sorted(set(skipped['path'])))})")


if __name__ == "__main__":
    main()
