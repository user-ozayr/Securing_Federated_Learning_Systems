"""Offline pilot for a moving-target defence against poisoning.

Reads the client updates recorded by the completion runs (instrumentation.npz:
per round and client the submitted update and whether the client was malicious)
and asks two questions before anything is built into SPDZ2k:

1. Magnitude. Where does each submitted update lie relative to the adaptive
   threshold T = lower median of the cohort's norms? If attackers sit at or
   below T, no threshold (static, hidden or moving) can reject them.
2. Direction. Does the cosine between a client's update and the mean of the
   other cohort members separate attackers from honest clients, on all
   coordinates and on secret random coordinate subsets (the moving-target
   variant: a fresh subset every round, unknown to clients)?

    python direction_pilot.py RUNS_DIR OUTPUT_DIR
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SUBSET_FRACTIONS = (1.0, 0.5, 0.25, 0.1)
SUBSET_DRAWS = 20
KEY = re.compile(r"r(\d{4})_c(\d{4})__(delta|malicious)")
# studies/conditions whose cohorts contain attackers; one record per run
STUDY_GLOBS = ("e1/e1__*", "e1x/e1x__*", "e2/e2__*", "e4/e4__*", "e5/e5__*")


GLOBAL = re.compile(r"r(\d{4})_global")


def load_rounds(npz_path: Path):
    """Per round: [(client, update, malicious)], and the global model after each round."""
    data = np.load(npz_path)
    rounds: dict[int, dict[int, dict]] = defaultdict(lambda: defaultdict(dict))
    globals_: dict[int, np.ndarray] = {}
    for name in data.files:
        match = KEY.fullmatch(name)
        if match:
            r, c, field = int(match[1]), int(match[2]), match[3]
            rounds[r][c][field] = data[name]
        elif (g := GLOBAL.fullmatch(name)):
            globals_[int(g[1])] = data[name].astype(np.float64)
    out = {}
    for r, clients in rounds.items():
        out[r] = [(c, v["delta"].astype(np.float64), bool(v["malicious"]))
                  for c, v in sorted(clients.items()) if "delta" in v and "malicious" in v]
    return out, globals_


def cohort_from_metadata(run_dir: Path) -> dict[int, set[int]] | None:
    """Selected clients per round as recorded by the run (guards against stale files)."""
    results = list(run_dir.glob("*_results.csv"))
    if not results:
        return None
    frame = pd.read_csv(results[0])
    column = "selected_client_ids" if "selected_client_ids" in frame else None
    if column is None:
        return None
    cohorts = {}
    for _, row in frame.iterrows():
        try:
            cohorts[int(row["round"])] = set(int(x) for x in json.loads(str(row[column])))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return cohorts


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0


def analyse_run(run_dir: Path, rng: np.random.Generator) -> list[dict]:
    rounds, globals_ = load_rounds(run_dir / "instrumentation.npz")
    cohorts = cohort_from_metadata(run_dir)
    meta = json.loads((run_dir / "run_metadata.json").read_text())
    config = (run_dir / "config.yaml").read_text()
    attack = re.search(r"attack_type:\s*(\S+)", config)
    rows = []
    for r, members in sorted(rounds.items()):
        if cohorts and r in cohorts:
            members = [m for m in members if m[0] in cohorts[r]]
        if len(members) < 3 or not any(m[2] for m in members):
            continue
        deltas = np.stack([m[1] for m in members])
        norms = np.linalg.norm(deltas, axis=1)
        threshold = float(np.sort(norms)[(len(norms) - 1) // 2])  # lower median
        total = deltas.sum(axis=0)
        dim = deltas.shape[1]
        subsets = {f: [rng.choice(dim, max(1, int(round(f * dim))), replace=False)
                       for _ in range(SUBSET_DRAWS if f < 1 else 1)] for f in SUBSET_FRACTIONS}
        # public reference: the update applied in the previous round (r-1 vs r-2)
        previous = (globals_[r - 1] - globals_[r - 2]
                    if (r - 1) in globals_ and (r - 2) in globals_ else None)
        for i, (client, delta, malicious) in enumerate(members):
            others = (total - delta) / (len(members) - 1)
            median_others = np.median(np.delete(deltas, i, axis=0), axis=0)
            row = {"run": run_dir.name, "study": run_dir.parent.name, "status": meta.get("status"),
                   "attack": attack[1] if attack else "?", "round": r, "client": client,
                   "malicious": malicious, "norm": float(norms[i]), "threshold": threshold,
                   "norm_over_threshold": float(norms[i] / threshold) if threshold > 0 else np.nan}
            for f, draws in subsets.items():
                # one secret subset per round in the defence; averaging over draws
                # estimates the expected score, the first draw is a single realisation
                values = [cosine(delta[s], others[s]) for s in draws]
                row[f"cos_{f:g}"] = float(np.mean(values))
                row[f"cos_{f:g}_single"] = float(values[0])
            row["cos_median"] = cosine(delta, median_others)
            for f in (0.25, 0.1):
                s = subsets[f][0]
                row[f"cos_median_{f:g}_single"] = cosine(delta[s], median_others[s])
            row["attackers_in_cohort"] = int(sum(m[2] for m in members))
            # sign agreement with the majority sign of the other clients (ties: >= 0
            # counts as positive); the MPC-friendly form of the direction check
            positive = deltas >= 0
            others_positive = np.delete(positive, i, axis=0).sum(axis=0)
            majority = 2 * others_positive >= len(members) - 1
            agree = positive[i] == majority
            row["sign_agree"] = float(agree.mean())
            for f in (0.25, 0.1):
                row[f"sign_agree_{f:g}_single"] = float(agree[subsets[f][0]].mean())
            row["cos_prev"] = cosine(delta, previous) if previous is not None else np.nan
            row["cos_prev_0.1_single"] = (cosine(delta[subsets[0.1][0]], previous[subsets[0.1][0]])
                                          if previous is not None else np.nan)
            rows.append(row)
    return rows


def auc(scores_pos: np.ndarray, scores_neg: np.ndarray) -> float:
    """P(score of a random attacker < score of a random honest client): low cosine = suspicious."""
    if len(scores_pos) == 0 or len(scores_neg) == 0:
        return float("nan")
    pos = scores_pos[:, None]
    neg = scores_neg[None, :]
    return float(((pos < neg).sum() + 0.5 * (pos == neg).sum()) / (pos.size * neg.size))


def tpr_at_fpr(scores_pos: np.ndarray, scores_neg: np.ndarray, fpr: float = 0.05) -> float:
    if len(scores_pos) == 0 or len(scores_neg) == 0:
        return float("nan")
    cut = np.quantile(scores_neg, fpr)
    return float((scores_pos < cut).mean())


def main() -> None:
    runs_dir, output = Path(sys.argv[1]), Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261121)
    rows = []
    for pattern in STUDY_GLOBS:
        for run_dir in sorted(runs_dir.glob(pattern)):
            if (run_dir / "instrumentation.npz").exists():
                rows.extend(analyse_run(run_dir, rng))
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "pilot_scores.csv", index=False)

    honest_all = frame[~frame.malicious]
    summary = []
    for attack, group in frame.groupby("attack"):
        bad = group[group.malicious]
        # honest reference from the same runs, so both come from the same trajectories
        good = group[~group.malicious]
        if bad.empty or good.empty:
            continue
        record = {"attack": attack, "attacker_participations": len(bad),
                  "honest_participations": len(good),
                  "attacker_norm_over_T_median": float(bad.norm_over_threshold.median()),
                  "attacker_share_at_or_below_T": float((bad.norm_over_threshold <= 1.0).mean()),
                  "attacker_share_at_or_below_2T": float((bad.norm_over_threshold <= 2.0).mean()),
                  "honest_norm_over_T_p95": float(good.norm_over_threshold.quantile(0.95))}
        for f in SUBSET_FRACTIONS:
            for kind in ("", "_single"):
                col = f"cos_{f:g}{kind}"
                record[f"auc_{col}"] = auc(bad[col].to_numpy(), good[col].to_numpy())
                record[f"tpr5_{col}"] = tpr_at_fpr(bad[col].to_numpy(), good[col].to_numpy())
            record[f"attacker_cos_{f:g}_median"] = float(bad[f"cos_{f:g}"].median())
            record[f"honest_cos_{f:g}_median"] = float(good[f"cos_{f:g}"].median())
        summary.append(record)
    table = pd.DataFrame(summary)
    table.to_csv(output / "pilot_summary.csv", index=False)
    cols = ["attack", "attacker_participations", "attacker_norm_over_T_median",
            "attacker_share_at_or_below_2T", "honest_norm_over_T_p95",
            "attacker_cos_1_median", "honest_cos_1_median",
            "auc_cos_1", "tpr5_cos_1", "auc_cos_0.25_single", "tpr5_cos_0.25_single",
            "auc_cos_0.1_single", "tpr5_cos_0.1_single"]
    pd.set_option("display.width", 250)
    print(table[cols].round(3).to_string(index=False))
    print(f"\n{len(frame)} participations, {frame.run.nunique()} runs, "
          f"{len(honest_all)} honest")


if __name__ == "__main__":
    main()
