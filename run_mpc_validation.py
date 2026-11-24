"""Validate the robust SPDZ2k aggregation program against exact references.

Requires Linux, a built MP-SPDZ v0.4.3 tree (FL_MPSPDZ_HOME) and spdz2k-party.x.

    FL_MPSPDZ_HOME=/path/to/MP-SPDZ-v0.4.3 python run_mpc_validation.py \
        --output-dir research_output/completion/experiments/mpc_validation
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from fl_security.evaluation.csv_safety import sanitize_csv_dataframe
from fl_security.smpc.validation import build_scenarios, run_scenarios


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dimension", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--parties", type=int, default=3)
    parser.add_argument("--only", nargs="*", default=None, help="scenario names to run")
    args = parser.parse_args()

    scenarios = build_scenarios(dimension=args.dimension, seed=args.seed)
    if args.only:
        scenarios = [s for s in scenarios if s.name in set(args.only)]
    output = Path(args.output_dir)
    results = run_scenarios(scenarios, output, party_count=args.parties)

    import pandas as pd

    rows = []
    for item in results:
        stats = item["party_statistics"]
        rows.append({
            "scenario": item["scenario"],
            "mode": item["config"]["mode"],
            "threshold": item["config"]["threshold"],
            "clients": item["clients"],
            "dimension": item["dimension"],
            "mpc_matches_reference_exactly": item["mpc_matches_reference_exactly"],
            "threshold_norm": item["threshold_norm"],
            "accepted": json.dumps(item["accepted"]),
            "clip_flags": json.dumps(item["clip_flags"]),
            "aggregate_norm": item["aggregate_norm"],
            "output_check_passed": item["output_check_passed"],
            "expected_output_check": item["expected_output_check"],
            "max_abs_error_vs_ideal_float_clipping": item["max_abs_error_vs_ideal_float_clipping"],
            "end_to_end_seconds": item["end_to_end_seconds"],
            "protocol_seconds_party0": stats[0].get("protocol_seconds"),
            "global_data_sent_mb": stats[0].get("global_data_sent_mb"),
        })
    frame = sanitize_csv_dataframe(pd.DataFrame(rows))
    frame.to_csv(output / "scenario_summary.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    failures = [r["scenario"] for r in results if not r["mpc_matches_reference_exactly"]]
    unexpected = [r["scenario"] for r in results if r["output_check_as_expected"] is False]
    print(json.dumps({"scenarios": len(results), "reference_mismatches": failures,
                      "unexpected_output_checks": unexpected}, indent=2))
    if failures or unexpected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
