"""Diagnostic plaintext replay with the arithmetic of the sum-only SPDZ2k path.

THIS IS NOT A SECURE-AGGREGATION RUN. SMPC stays disabled and no MPC party is
started. In this process only, the strategy's plaintext FedAvg
(``flower_simulation.weighted_fedavg``) is replaced by a plaintext emulation of
what the sum-only SPDZ2k path computes:

* each client state is encoded with the production encoder
  (``mp_spdz._encode_weighted_model``: ``round(float64(w) * n * S)`` as int64,
  including its ring-range guard);
* the integer vectors are added exactly (the parties add in Z_2^64; the sum is
  checked to stay inside the signed 64-bit range, so no wrap-around occurs);
* the sum is decoded as in ``mp_spdz.receive_weighted_average``:
  ``float64(sum) / S / N``, cast to the model dtype.

Data, partition, seeds, cohort, local training and evaluation are the unchanged
code path of the given plaintext configuration. The purpose is to test whether
the sum-only SPDZ2k trajectories are reproduced by their plaintext arithmetic
and how the result depends on the scale S.

Usage (repository root, PYTHONPATH=src, same thread settings as the suite):
  python research_output/completion/tools/sum_only_replay.py \
      --config <config.yaml of a plaintext FedAvg run> --scale 1000000 \
      --name <experiment name> --output-dir <new directory> \
      [--compare label=<study>/<run_id> ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import torch
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                          check=False).stdout.strip()


def make_fixed_point_fedavg(scale: int, max_clients: int, calls: list):
    from fl_security.smpc.fixed_point import FixedPointEncoder
    from fl_security.smpc.mp_spdz import _encode_weighted_model

    encoder = FixedPointEncoder(scale)

    def fixed_point_fedavg(client_states, num_examples, global_state):
        if not client_states or len(client_states) != len(num_examples):
            raise ValueError("client_states and num_examples must be non-empty and aligned")
        summed, total = None, 0
        for state, count in zip(client_states, num_examples):
            ordered = {key: state[key] for key in global_state}
            values, _ = _encode_weighted_model(ordered, int(count), encoder, max_clients)
            total += values[-1]
            body = values[:-1]
            summed = list(body) if summed is None else [a + b for a, b in zip(summed, body)]
        if total != sum(num_examples):
            raise RuntimeError("encoded sample counts do not add up")
        if any(abs(value) >= 1 << 63 for value in summed):
            raise OverflowError("aggregate leaves the signed 64-bit ring range")
        result, offset = {}, 0
        for key, base in global_state.items():
            if not torch.is_floating_point(base):
                result[key] = base.detach().clone()
                continue
            count = base.numel()
            weighted = torch.tensor(summed[offset: offset + count], dtype=torch.float64).reshape(base.shape)
            result[key] = (weighted / encoder.scale / total).to(device=base.device, dtype=base.dtype)
            offset += count
        if offset != len(summed):
            raise RuntimeError("decoded length does not match the model schema")
        calls.append(len(client_states))
        return result

    return fixed_point_fedavg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--scale", required=True, type=int)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--compare", action="append", default=[],
                        help="label=<study>/<run_id> of a suite run to compare with")
    args = parser.parse_args()

    from fl_security.config import load_config
    import fl_security.federated.flower_simulation as simulation
    from fl_security.experiments.analysis import analyze_run

    output_dir = Path(args.output_dir).resolve()
    runs_root = (REPO_ROOT / "research_output" / "completion" / "experiments" / "runs").resolve()
    if output_dir == runs_root or runs_root in output_dir.parents:
        raise SystemExit("refusing to write a replay into the suite's run directories")
    if output_dir.exists() and any(p.name != "run.log" for p in output_dir.iterdir()):
        raise SystemExit(f"output directory {output_dir} is not empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    source = Path(args.config)
    config = load_config(str(source))
    smpc = config.get("smpc", {}) or {}
    defences = config.get("defences", {}) or {}
    if smpc.get("enabled"):
        raise SystemExit("the replay starts from a plaintext configuration (smpc.enabled must be false)")
    if any((defences.get(name) or {}).get("enabled") for name in ("robust_aggregation", "norm_defence_reference")):
        raise SystemExit("the replay starts from a plain FedAvg configuration (no defence)")
    if (config.get("mtd", {}) or {}).get("schedule") not in (None, "static", "deterministic"):
        raise SystemExit("secret MTD schedules cannot be replayed")
    config["experiment"]["name"] = args.name
    config.setdefault("evaluation", {})["output_dir"] = str(output_dir)
    config["evaluation"]["instrumentation"] = True
    config_text = yaml.safe_dump(config, sort_keys=True)
    (output_dir / "config.yaml").write_text(config_text, encoding="utf-8")

    calls: list[int] = []
    patched = make_fixed_point_fedavg(args.scale, int(config["federated_learning"]["num_clients"]), calls)
    simulation.weighted_fedavg = patched
    metadata = {
        "purpose": "plaintext diagnostic replay of the sum-only SPDZ2k arithmetic; not a secure run",
        "aggregation": "weighted_fedavg replaced in-process by round(float64(w)*n*S) per client, "
                       "exact integer sum, float64(sum)/S/N cast to float32",
        "scale": args.scale,
        "source_config": str(source),
        "source_config_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
        "compare_with": dict(item.split("=", 1) for item in args.compare),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty_tracked": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "host": platform.node(), "python": sys.version.split()[0],
        "threads": {name: os.environ.get(name) for name in
                    ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "pythonpath": os.environ.get("PYTHONPATH"),
        "fl_security_module": simulation.__file__,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "running",
    }
    metadata_path = output_dir / "replay_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    started = time.perf_counter()
    try:
        simulation.run_flower_simulation(config)
        if simulation.weighted_fedavg is not patched:
            raise RuntimeError("the aggregation patch was not in effect")
        metadata["aggregations_replaced"] = len(calls)
        if len(calls) != int(config["experiment"]["rounds"]):
            raise RuntimeError(f"expected {config['experiment']['rounds']} replaced aggregations, got {len(calls)}")
        metadata["analysis"] = analyze_run(output_dir, config)
        metadata["status"] = "completed"
    except BaseException as error:
        metadata["status"] = "failed"
        metadata["error"] = f"{type(error).__name__}: {error}"[-2000:]
        raise
    finally:
        metadata["wall_seconds"] = round(time.perf_counter() - started, 3)
        metadata["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        metadata_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
