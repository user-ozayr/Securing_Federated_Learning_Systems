"""Resumable execution of the experiment grid.

Each run is executed in a separate process group (``run_experiment.py``) with a
timeout, so Ray and MP-SPDZ state cannot leak between runs. For secret-derived
MTD schedules a fresh random FL_MTD_SECRET is generated per run; only its
SHA-256 commitment is stored. Completed runs are skipped when the suite is
restarted.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

from fl_security.experiments.grid import RunSpec, all_runs

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=False
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _kill_group(process: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=15)
            return
        except subprocess.TimeoutExpired:
            continue


def _cleanup_stray_processes() -> None:
    """Stop Ray and any leftover MP-SPDZ party binaries from a failed run."""
    ray = Path(sys.executable).with_name("ray")
    if ray.exists():
        subprocess.run([str(ray), "stop", "--force"], capture_output=True, timeout=120, check=False)
    subprocess.run(["pkill", "-f", "[s]pdz2k-party.x"], capture_output=True, check=False)


def run_one(spec: RunSpec, output_root: Path, timeout_seconds: int) -> dict:
    run_dir = output_root / "runs" / spec.study / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(json.dumps(spec.config))
    config["evaluation"]["output_dir"] = str(run_dir.resolve())
    config_dir = output_root / "configs" / spec.study
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"{spec.run_id}.yaml"
    config_text = yaml.safe_dump(config, sort_keys=True)
    config_path.write_text(config_text, encoding="utf-8")
    (run_dir / "config.yaml").write_text(config_text, encoding="utf-8")

    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "FL_MPSPDZ_STARTUP_TIMEOUT": env.get("FL_MPSPDZ_STARTUP_TIMEOUT", "0.5"),
        "RAY_DEDUP_LOGS": "0",
    })
    commitment = None
    env.pop("FL_MTD_SECRET", None)
    if spec.needs_secret:
        secret = secrets.token_urlsafe(48)
        env["FL_MTD_SECRET"] = secret
        commitment = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        del secret
    command = [sys.executable, str(REPO_ROOT / "run_experiment.py"), "--config", str(config_path)]
    if spec.uses_mpc:
        command.append("--local-mp-spdz")

    metadata = {
        "run_id": spec.run_id, "study": spec.study, "condition": spec.condition,
        "attack": spec.attack, "seed": spec.seed, "uses_mpc": spec.uses_mpc,
        "mtd_schedule": config.get("mtd", {}).get("schedule"),
        "mtd_secret_sha256_commitment": commitment,
        "config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "host": platform.node(), "python": sys.version.split()[0],
        "command": " ".join(command[1:]),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "load_average_start": os.getloadavg(),
    }
    log_path = run_dir / "run.log"
    started = time.perf_counter()
    status = "failed"
    detail = ""
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            return_code = process.wait(timeout=timeout_seconds)
            detail = f"exit code {return_code}"
            results = list(run_dir.glob("*_results.csv"))
            status = "completed" if return_code == 0 and results else "failed"
        except subprocess.TimeoutExpired:
            _kill_group(process)
            status, detail = "timeout", f"exceeded {timeout_seconds} s"
        except KeyboardInterrupt:
            _kill_group(process)
            raise
    if status != "completed":
        _cleanup_stray_processes()
    metadata.update({
        "status": status, "detail": detail,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "load_average_end": os.getloadavg(),
    })
    if status == "completed":
        try:
            from fl_security.experiments.analysis import analyze_run

            metadata["analysis"] = analyze_run(run_dir, config)
        except Exception as exc:  # analysis problems must not hide the run itself
            metadata["analysis_error"] = repr(exc)
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    return metadata


def run_suite(output_root: Path, studies: list[str] | None, timeout_seconds: int,
              max_runs: int | None = None, only_mpc: bool | None = None, dry_run: bool = False) -> None:
    runs = all_runs(studies)
    if only_mpc is not None:
        runs = [run for run in runs if run.uses_mpc == only_mpc]
    progress = output_root / "suite_progress.jsonl"
    output_root.mkdir(parents=True, exist_ok=True)
    executed = 0
    for index, spec in enumerate(runs, 1):
        meta_path = output_root / "runs" / spec.study / spec.run_id / "run_metadata.json"
        if meta_path.exists():
            try:
                if json.loads(meta_path.read_text(encoding="utf-8")).get("status") == "completed":
                    continue
            except json.JSONDecodeError:
                pass
        if dry_run:
            print(f"[{index}/{len(runs)}] would run {spec.run_id} (mpc={spec.uses_mpc})")
            continue
        if max_runs is not None and executed >= max_runs:
            break
        print(f"[{index}/{len(runs)}] {spec.run_id}", flush=True)
        metadata = run_one(spec, output_root, timeout_seconds)
        executed += 1
        with progress.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({k: metadata[k] for k in (
                "run_id", "status", "wall_seconds", "finished_utc")}) + "\n")
        print(f"    -> {metadata['status']} in {metadata['wall_seconds']} s", flush=True)
