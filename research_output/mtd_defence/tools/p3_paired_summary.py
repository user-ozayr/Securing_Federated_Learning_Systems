"""Paired comparison for the P3 study (same secret cohorts and subsets per seed).

    python research_output/mtd_defence/tools/p3_paired_summary.py research_output/mtd_defence/experiments

Reads p3_runs.csv (written by m1_summary.py ... p3). Per attack: final ASR per
seed and condition, and the per-seed difference of the full combination (secret
MTD + secret direction screen) against each other condition, with the mean
difference and how many seeds favour the combination.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

FULL = "reference_direction_secret_mtd_t52"
OTHERS = ["reference_defence", "reference_direction_secret_t52", "reference_defence_mtd"]


def main() -> None:
    root = Path(sys.argv[1])
    runs = pd.read_csv(root / "p3_runs.csv")
    rows = []
    pd.set_option("display.width", 200)
    for attack, frame in runs.groupby("attack", sort=False):
        table = frame.pivot_table(index="seed", columns="condition", values="asr")
        print(f"\n== {attack}: final ASR per seed\n{table.round(3).to_string()}")
        for other in OTHERS:
            if FULL not in table or other not in table:
                continue
            diff = (table[FULL] - table[other]).dropna()
            rows.append({"attack": attack, "versus": other, "seeds": len(diff),
                         "mean_asr_full": round(float(table[FULL].mean()), 3),
                         "mean_asr_other": round(float(table[other].mean()), 3),
                         "mean_difference": round(float(diff.mean()), 3),
                         "seeds_full_lower": int((diff < 0).sum()),
                         "seeds_full_higher": int((diff > 0).sum())})
    summary = pd.DataFrame(rows)
    summary.to_csv(root / "p3_paired_differences.csv", index=False)
    print("\n== paired differences (full combination minus other; negative = lower ASR)")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
