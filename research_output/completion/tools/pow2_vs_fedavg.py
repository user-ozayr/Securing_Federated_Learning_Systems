"""Compare each power-of-two SPDZ2k run with plaintext FedAvg.

Run this script from the repository root:

    python research_output/completion/tools/pow2_vs_fedavg.py

For each attack and seed, it compares per-round loss, accuracy, and ASR for
both sum-only variants with the matching plaintext FedAvg run. The rerun uses
S = 2^40; the original run uses S = 10^6.

A run is identical when every recorded round matches. If a fail-closed abort
matches through the last completed round, the report says it matched until the
abort. The script writes experiments_pow2/pow2_vs_fedavg.csv and prints a
summary.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "experiments" / "runs" / "e1"
POW2 = ROOT / "experiments_pow2" / "runs" / "e1"
METRICS = ("global_loss", "global_accuracy", "backdoor_asr")
VARIANTS = (("S=2^40 (rerun)", POW2), ("S=10^6 (original)", ORIGINAL))


def _read_run_rounds(run_dir: Path):
    results = next(run_dir.glob("*_results.csv"), None)
    if results is None:
        return None
    meta = run_dir / "run_metadata.json"
    status = json.loads(meta.read_text(encoding="utf-8")).get("status") if meta.exists() else "unknown"
    rows = {}
    with results.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            # Compare the recorded strings exactly. An unmeasured metric is an empty string.
            rows[int(row["round"])] = tuple(row.get(m, "") for m in METRICS)
    return status, rows


def _absolute_accuracy_gap(candidate_metrics: tuple, reference_metrics: tuple) -> float:
    try:
        return abs(float(candidate_metrics[1]) - float(reference_metrics[1]))
    except ValueError:
        return 0.0


def compare_run_outputs(candidate_run: Path, reference_run: Path) -> dict:
    candidate_data = _read_run_rounds(candidate_run)
    reference_data = _read_run_rounds(reference_run)
    if candidate_data is None or reference_data is None:
        return {"available": False}

    candidate_status, candidate_rounds = candidate_data
    _, reference_rounds = reference_data
    common_rounds = sorted(set(candidate_rounds) & set(reference_rounds))
    differing_rounds = [
        round_num for round_num in common_rounds
        if candidate_rounds[round_num] != reference_rounds[round_num]
    ]
    if not differing_rounds and set(candidate_rounds) == set(reference_rounds):
        verdict = "identical"
    elif not differing_rounds:
        verdict = (
            "identical until abort" if candidate_status == "aborted"
            else "identical, fewer rounds"
        )
    else:
        verdict = "differs"
    return {
        "available": True, "status": candidate_status, "verdict": verdict,
        "rounds": max(candidate_rounds, default=0),
        "reference_rounds": max(reference_rounds, default=0),
        "first_differing_round": differing_rounds[0] if differing_rounds else "",
        "max_abs_accuracy_difference": round(max(
            (_absolute_accuracy_gap(candidate_rounds[r], reference_rounds[r])
             for r in common_rounds), default=0.0), 4),
    }


def main() -> None:
    rows = []
    for baseline in sorted(ORIGINAL.glob("e1__baseline__*")):
        _, _, attack, seed = baseline.name.split("__")
        for label, root in VARIANTS:
            result = compare_run_outputs(root / f"e1__smpc_only__{attack}__{seed}", baseline)
            rows.append({"attack": attack, "seed": seed, "variant": label, **result})
    output = POW2.parents[1] / "pow2_vs_fedavg.csv"
    fields = ["attack", "seed", "variant", "available", "status", "verdict", "rounds",
              "reference_rounds", "first_differing_round", "max_abs_accuracy_difference"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)
    for label, _ in VARIANTS:
        variant_results = [
            row for row in rows if row["variant"] == label and row["available"]
        ]
        verdict_counts = {}
        for result in variant_results:
            verdict = result["verdict"]
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        print(f"{label}: {len(variant_results)} of 18 runs available; " +
              ", ".join(f"{verdict}: {count}" for verdict, count in sorted(verdict_counts.items())))
        for r in variant_results:
            if r["verdict"] != "identical":
                print(f"    {r['attack']}__{r['seed']}: {r['verdict']} (status {r['status']}, "
                      f"rounds {r['rounds']}/{r['reference_rounds']}, first differing round "
                      f"{r['first_differing_round'] or '-'}, max |d accuracy| "
                      f"{r['max_abs_accuracy_difference']})")
    print(f"written: {output}")


if __name__ == "__main__":
    main()
