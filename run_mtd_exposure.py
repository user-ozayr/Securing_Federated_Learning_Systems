"""Monte-Carlo exposure study for static, deterministic and secret MTD schedules.

    python run_mtd_exposure.py --output-dir research_output/completion/experiments/mtd_exposure
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fl_security.evaluation.csv_safety import sanitize_csv_dataframe
from fl_security.mtd.simulation import run_exposure_study


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--rounds", type=int, nargs="+", default=[10, 100])
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for rounds in args.rounds:
        raw, summary = run_exposure_study(rounds=rounds, trials=args.trials)
        sanitize_csv_dataframe(raw).to_csv(output / f"exposure_raw_R{rounds}.csv", index=False)
        sanitize_csv_dataframe(summary).to_csv(output / f"exposure_summary_R{rounds}.csv", index=False)
        table = summary[summary["metric"].isin(
            ["mean_malicious_share", "rounds_with_malicious_majority", "compromise_hit_rate",
             "prediction_accuracy"])].pivot_table(
            index=["budget", "schedule", "adversary"], columns="metric", values="mean")
        print(f"R={rounds}\n{table.round(3).to_string()}")


if __name__ == "__main__":
    main()
