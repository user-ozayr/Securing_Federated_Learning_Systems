"""Cost of the direction screen inside SPDZ2k at the deployed model size.

    python research_output/mtd_defence/tools/direction_benchmark.py OUTPUT_DIR

Real three-party SPDZ2k rounds (local parties) with d = 2,202 and K = 4: the
norm defence alone, and with the direction screen on a 10 % and a 25 % secret
subset; two repetitions each. Every round is also checked bit for bit against
robust_reference (validation harness).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from fl_security.smpc.robust import SecureDefenceConfig, direction_key
from fl_security.smpc.validation import Scenario, _vector, run_scenarios

DIMENSION = 2202
REPETITIONS = 2


def scenarios() -> list[Scenario]:
    rng = random.Random(11)
    out = []
    for fraction in (None, 0.10, 0.25):
        cfg = SecureDefenceConfig(
            mode="clip_screen", threshold="adaptive", median_multiplier_squared=1,
            screen_multiplier_squared=4, min_norm=0.25, max_norm=16.0, max_valid_norm=64.0,
            fractional_bits=14, clip_bits=8,
            direction_check=fraction is not None, direction_subset="secret",
            direction_fraction=fraction or 0.25, direction_min_agreement=0.52)
        for repetition in range(REPETITIONS):
            inputs = [_vector(n, DIMENSION, cfg.scale, rng) for n in (2.5, 3.0, 3.5, 3.2)]
            direction = None
            if fraction is not None:
                indices = cfg.direction_indices(DIMENSION, direction_key(b"benchmark-key-material!", repetition))
                direction = {"min_agree": cfg.min_agreement_count(len(indices)), "indices": indices}
            label = "none" if fraction is None else f"{int(fraction * 100)}pct"
            out.append(Scenario(f"bench_{label}_r{repetition}", f"d={DIMENSION}, K=4, subset {label}",
                                cfg, [5000] * 4, inputs, expect_output_check=None,
                                direction=direction))
    return out


def main() -> None:
    output = Path(sys.argv[1])
    results = run_scenarios(scenarios(), output)
    rows = []
    for r in results:
        stats = r.get("party_statistics") or []
        rows.append({
            "scenario": r["scenario"], "subset_size": r["direction_subset_size"],
            "bit_exact": r["mpc_matches_reference_exactly"],
            "end_to_end_seconds": round(r["end_to_end_seconds"], 2),
            "party_statistics": stats,
        })
    (output / "benchmark_summary.json").write_text(json.dumps(rows, indent=2))
    for row in rows:
        print(row["scenario"], row["subset_size"], row["bit_exact"], row["end_to_end_seconds"])


if __name__ == "__main__":
    main()
