"""Run and resume the configured experiment grid.

Each experiment runs in its own process group. If it times out, Ray and MP-SPDZ
state are cleaned up before the next run. Unpaired MTD runs receive a fresh
random FL_MTD_SECRET; the metadata stores only its SHA-256 commitment.

Paired studies derive one secret for each (study, seed), so every condition in
that pair sees the same secret cohorts and direction subsets. This common-random
number setup uses a 32-byte suite key stored on the host as pairing_key with
mode 0600. The simulated adversary never receives that key.

Completed runs are skipped on restart. Before an unfinished run is retried,
its files move to failed_attempts/<UTC stamp>_auto/ so the retry starts in an
empty directory.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

from fl_security.experiments.grid import RunSpec, all_runs

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git_output(*args: str) -> str:
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


def set_aside_previous_attempt(run_dir: Path, output_root: Path, study: str) -> Path | None:
    """Move the files of an earlier, unfinished attempt out of ``run_dir``.

    A repeated run must not inherit files of an earlier attempt: per-client
    instrumentation of a different cohort would be mixed into the analysis, and
    an old ``*_abort.json`` would be taken for the status of the repeat.
    Nothing is deleted; the attempt is moved to ``failed_attempts``.
    """
    if not run_dir.is_dir() or not any(run_dir.iterdir()):
        return None
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    target = output_root / "failed_attempts" / f"{stamp}_auto" / study / run_dir.name
    suffix = 1
    while target.exists():
        suffix += 1
        target = output_root / "failed_attempts" / f"{stamp}_auto{suffix}" / study / run_dir.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(run_dir), str(target))
    return target


PAIRING_KEY_FILE = "pairing_key"


def load_pairing_key(output_root: Path) -> bytes:
    """The suite's pairing key; created once (32 random bytes, mode 0600) so that a
    resumed suite derives the same per-seed secrets."""
    path = output_root / PAIRING_KEY_FILE
    if not path.exists():
        output_root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(secrets.token_hex(32))
    key = bytes.fromhex(path.read_text(encoding="ascii").strip())
    if len(key) != 32:
        raise ValueError(f"{path} must hold 32 bytes in hex")
    return key


def paired_secret(pairing_key: bytes, study: str, seed: int) -> str:
    """FL_MTD_SECRET shared by every condition of (study, seed); 43 characters."""
    digest = hmac.new(pairing_key, f"paired-mtd-secret|{study}|seed={int(seed)}".encode("utf-8"),
                      hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def run_one(spec: RunSpec, output_root: Path, timeout_seconds: int,
            pairing_key: bytes | None = None) -> dict:
    run_dir = output_root / "runs" / spec.study / spec.run_id
    previous_attempt = set_aside_previous_attempt(run_dir, output_root, spec.study)
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
    paired = bool(spec.tags.get("paired"))
    if paired and (spec.needs_secret or spec.uses_secret_subset):
        if pairing_key is None:
            raise ValueError(f"{spec.run_id} is paired but no pairing key was supplied")
        secret = paired_secret(pairing_key, spec.study, spec.seed)
        env["FL_MTD_SECRET"] = secret
        commitment = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        del secret
    elif spec.needs_secret:
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
        "paired_secret": paired and commitment is not None,
        "pairing_key_sha256": (hashlib.sha256(pairing_key).hexdigest()
                               if paired and pairing_key is not None else None),
        "config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
        "git_commit": _git_output("rev-parse", "HEAD"),
        "git_dirty": bool(_git_output("status", "--porcelain", "--untracked-files=no")),
        "host": platform.node(), "python": sys.version.split()[0],
        "command": " ".join(command[1:]),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "load_average_start": os.getloadavg(),
        "previous_attempt_moved_to": str(previous_attempt) if previous_attempt else None,
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
            abort_files = list(run_dir.glob("*_abort.json"))
            if return_code == 0 and results:
                status = "completed"
            elif results and abort_files:
                # Fail-closed abort (e.g. a secure round refused to encode a
                # diverged model): partial per-round results are kept.
                status = "aborted"
                abort = json.loads(abort_files[0].read_text(encoding="utf-8"))
                detail = (f"aborted after round {abort.get('rounds_completed')}: "
                          f"{abort.get('cause_type')}: {abort.get('cause', '')[-300:]}")
            else:
                status = "failed"
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
    if status in ("completed", "aborted"):
        try:
            from fl_security.experiments.analysis import analyze_run

            metadata["analysis"] = analyze_run(run_dir, config)
        except Exception as exc:  # analysis problems must not hide the run itself
            metadata["analysis_error"] = repr(exc)
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    return metadata


def run_suite(output_root: Path, studies: list[str] | None, timeout_seconds: int,
              max_runs: int | None = None, only_mpc: bool | None = None, dry_run: bool = False,
              conditions: list[str] | None = None) -> None:
    runs = all_runs(studies)
    if only_mpc is not None:
        runs = [run for run in runs if run.uses_mpc == only_mpc]
    if conditions:
        selected_conditions = set(conditions)
        runs = [run for run in runs if run.condition in selected_conditions]
    progress = output_root / "suite_progress.jsonl"
    output_root.mkdir(parents=True, exist_ok=True)
    pairing_key = (load_pairing_key(output_root)
                   if not dry_run and any(run.tags.get("paired") for run in runs) else None)
    executed = 0
    for index, spec in enumerate(runs, 1):
        meta_path = output_root / "runs" / spec.study / spec.run_id / "run_metadata.json"
        if meta_path.exists():
            try:
                # completed and fail-closed aborted runs are deterministic outcomes
                if json.loads(meta_path.read_text(encoding="utf-8")).get("status") in ("completed", "aborted"):
                    continue
            except json.JSONDecodeError:
                pass
        if dry_run:
            print(f"[{index}/{len(runs)}] would run {spec.run_id} (mpc={spec.uses_mpc})")
            continue
        if max_runs is not None and executed >= max_runs:
            break
        print(f"[{index}/{len(runs)}] {spec.run_id}", flush=True)
        metadata = run_one(spec, output_root, timeout_seconds, pairing_key)
        executed += 1
        with progress.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({k: metadata[k] for k in (
                "run_id", "status", "wall_seconds", "finished_utc")}) + "\n")
        print(f"    -> {metadata['status']} in {metadata['wall_seconds']} s", flush=True)
