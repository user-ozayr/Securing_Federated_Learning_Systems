"""E6 update-leakage study: what the coordinator can reconstruct, FedAvg vs SPDZ2k.

    # Run as one process.
    python run_leakage_study.py --output-dir research_output/completion/experiments/leakage/evaluation
    # Or run three shards in parallel and merge their results.
    python run_leakage_study.py --output-dir DIR --shard 0 --num-shards 3   (and 1, 2)
    python run_leakage_study.py --output-dir DIR --merge
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from fl_security.attacks.gradient_inversion import InversionSettings
from fl_security.evaluation.csv_safety import sanitize_csv_dataframe
from fl_security.experiments.leakage import (
    LeakageConfig,
    config_record,
    iterate_trials,
    prepare_models,
    run_trial,
    summarise,
)

REPO_ROOT = Path(__file__).resolve().parent
# Files that define the study; hashed into the metadata for provenance.
SOURCES = (
    "run_leakage_study.py",
    "src/fl_security/attacks/gradient_inversion.py",
    "src/fl_security/experiments/leakage.py",
    "src/fl_security/smpc/fixed_point.py",
    "src/fl_security/smpc/mp_spdz.py",
    "src/fl_security/federated/training.py",
    "src/fl_security/federated/model.py",
    "src/fl_security/federated/dataset.py",
)
ATTACKS = ("optimisation", "fc_features", "fc_input")


def _git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                            check=False)
    return result.stdout.strip()


def _build_run_metadata(cfg: LeakageConfig, args) -> dict:
    return {
        "study": "e6_update_leakage",
        "git_commit": _git_output("rev-parse", "HEAD"),
        "git_dirty": bool(_git_output("status", "--porcelain", "--untracked-files=no")),
        "source_sha256": {p: hashlib.sha256((REPO_ROOT / p).read_bytes()).hexdigest()
                          for p in SOURCES},
        "python": platform.python_version(), "torch": torch.__version__,
        "host": platform.machine(), "threads": args.threads,
        "attacks": list(args.attacks), "shard": args.shard, "num_shards": args.num_shards,
        "config": config_record(cfg),
    }


def _write_leakage_summary(output: Path, raw: pd.DataFrame, cfg: LeakageConfig) -> None:
    summary = summarise(raw, cfg.recognisable_ssim)
    sanitize_csv_dataframe(summary).to_csv(output / "leakage_summary.csv", index=False)
    table = summary[summary["metric"].isin(["ssim", "feature_cosine", "label_recall"])]
    print(table.pivot_table(index=["attack", "model_state", "batch_size", "view"],
                            columns="metric", values="mean").round(3).to_string())


def merge_shards(output: Path, cfg: LeakageConfig) -> None:
    shards = sorted(path for path in output.glob("shard_*") if path.is_dir())
    if not shards:
        raise SystemExit(f"no shard directories in {output}")
    raw = pd.concat([pd.read_csv(s / "leakage_raw.csv") for s in shards], ignore_index=True)
    raw = raw.sort_values(["attack", "model_state", "batch_size", "view", "trial", "image_index"])
    sanitize_csv_dataframe(raw).to_csv(output / "leakage_raw.csv", index=False)
    examples: dict[str, np.ndarray] = {}
    for shard in shards:
        with np.load(shard / "leakage_examples.npz") as data:
            examples.update({k: data[k] for k in data.files})
    np.savez_compressed(output / "leakage_examples.npz", **examples)
    _write_leakage_summary(output, raw, cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--trials", type=int, default=6)
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--model-states", nargs="+", default=["initial", "trained"])
    parser.add_argument("--attacks", nargs="+", choices=ATTACKS, default=list(ATTACKS))
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--restarts", type=int, default=2)
    parser.add_argument("--attack-lr", type=float, default=0.1)
    parser.add_argument("--tv-weight", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--merge", action="store_true", help="combine shard_* results")
    args = parser.parse_args()
    if not 0 <= args.shard < args.num_shards:
        parser.error("--shard must be in [0, --num-shards)")

    torch.set_num_threads(args.threads)
    cfg = LeakageConfig(batch_sizes=tuple(args.batch_sizes), model_states=tuple(args.model_states),
                        trials=args.trials, seed=args.seed,
                        inversion=InversionSettings(iterations=args.iterations,
                                                    restarts=args.restarts,
                                                    learning_rate=args.attack_lr,
                                                    tv_weight=args.tv_weight))
    output = Path(args.output_dir)
    if args.merge:
        merge_shards(output, cfg)
        return
    if args.num_shards > 1:
        output = output / f"shard_{args.shard}"
    output.mkdir(parents=True, exist_ok=True)
    metadata = _build_run_metadata(cfg, args)
    metadata["started_unix"] = time.time()
    partitions, models, info = prepare_models(cfg, args.data_root)
    metadata.update(info)

    rows: list[dict] = []
    examples: dict[str, np.ndarray] = {}
    for index, (state, batch, trial) in enumerate(iterate_trials(cfg)):
        if index % args.num_shards != args.shard:
            continue
        t0 = time.time()
        trial_rows, trial_examples = run_trial(cfg, models[state], partitions, state, batch,
                                               trial, args.attacks)
        rows.extend(trial_rows)
        if trial == 0:
            examples.update({f"{state}__b{batch}__{k}": v for k, v in trial_examples.items()})
        print(f"{state} B={batch} trial={trial} {time.time() - t0:.1f}s", flush=True)
        sanitize_csv_dataframe(pd.DataFrame(rows)).to_csv(output / "leakage_raw.csv", index=False)

    np.savez_compressed(output / "leakage_examples.npz", **examples)
    metadata["finished_unix"] = time.time()
    metadata["elapsed_seconds"] = metadata["finished_unix"] - metadata["started_unix"]
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    if args.num_shards == 1:
        _write_leakage_summary(output, pd.DataFrame(rows), cfg)


if __name__ == "__main__":
    main()
