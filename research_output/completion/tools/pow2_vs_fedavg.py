"""Sum-only SPDZ2k at S = 2^40 against plaintext FedAvg, run by run.

    python research_output/completion/tools/pow2_vs_fedavg.py

For every attack and seed, compares the per-round loss, accuracy and ASR of
  * experiments_pow2/runs/e1/e1__smpc_only__*  (rerun, S = 2^40) and
  * experiments/runs/e1/e1__smpc_only__*       (original, S = 10^6)
with the seed-matched plaintext FedAvg run experiments/runs/e1/e1__baseline__*.
A run is "identical" when every recorded round matches exactly; a fail-closed
abort that matches up to the abort is reported as identical until the abort.
Writes experiments_pow2/pow2_vs_fedavg.csv and prints a summary.
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


def _rounds(run_dir: Path):
    results = next(run_dir.glob("*_results.csv"), None)
    if results is None:
        return None
    meta = run_dir / "run_metadata.json"
    status = json.loads(meta.read_text(encoding="utf-8")).get("status") if meta.exists() else "unknown"
    rows = {}
    with results.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            # recorded text, compared exactly; a metric not measured in a round is ""
            rows[int(row["round"])] = tuple(row.get(m, "") for m in METRICS)
    return status, rows


def _accuracy_gap(x: tuple, y: tuple) -> float:
    try:
        return abs(float(x[1]) - float(y[1]))
    except ValueError:
        return 0.0


def compare(candidate: Path, reference: Path) -> dict:
    a, b = _rounds(candidate), _rounds(reference)
    if a is None or b is None:
        return {"available": False}
    (status, rows_a), (_, rows_b) = a, b
    common = sorted(set(rows_a) & set(rows_b))
    differing = [r for r in common if rows_a[r] != rows_b[r]]
    if not differing and set(rows_a) == set(rows_b):
        verdict = "identical"
    elif not differing:
        verdict = "identical until abort" if status == "aborted" else "identical, fewer rounds"
    else:
        verdict = "differs"
    return {
        "available": True, "status": status, "verdict": verdict,
        "rounds": max(rows_a, default=0), "reference_rounds": max(rows_b, default=0),
        "first_differing_round": differing[0] if differing else "",
        "max_abs_accuracy_difference": round(max(
            (_accuracy_gap(rows_a[r], rows_b[r]) for r in common), default=0.0), 4),
    }


def main() -> None:
    rows = []
    for baseline in sorted(ORIGINAL.glob("e1__baseline__*")):
        _, _, attack, seed = baseline.name.split("__")
        for label, root in VARIANTS:
            result = compare(root / f"e1__smpc_only__{attack}__{seed}", baseline)
            rows.append({"attack": attack, "seed": seed, "variant": label, **result})
    output = POW2.parents[1] / "pow2_vs_fedavg.csv"
    fields = ["attack", "seed", "variant", "available", "status", "verdict", "rounds",
              "reference_rounds", "first_differing_round", "max_abs_accuracy_difference"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)
    for label, _ in VARIANTS:
        mine = [r for r in rows if r["variant"] == label and r["available"]]
        counts = {}
        for r in mine:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        print(f"{label}: {len(mine)} of 18 runs available; " +
              ", ".join(f"{v}: {n}" for v, n in sorted(counts.items())))
        for r in mine:
            if r["verdict"] != "identical":
                print(f"    {r['attack']}__{r['seed']}: {r['verdict']} (status {r['status']}, "
                      f"rounds {r['rounds']}/{r['reference_rounds']}, first differing round "
                      f"{r['first_differing_round'] or '-'}, max |d accuracy| "
                      f"{r['max_abs_accuracy_difference']})")
    print(f"written: {output}")


if __name__ == "__main__":
    main()
