"""Controlled SPDZ2k benchmarks for the sum-only and robust aggregation programs.

Each benchmark executes one complete secure round on local party services with
synthetic honest-format client updates and records:

* coordinator-side wall times (start/compile+launch, client input, output, finish);
* MP-SPDZ's own measurements per party (protocol seconds, data sent, rounds);
* compiler resource counts (triples, random bits, opens) from a compile-only pass;
* peak resident memory of the party processes (sampled from /proc);
* numerical error of the revealed aggregate against the exact/plaintext reference.

A watchdog aborts the benchmark if available memory or disk drops below a floor
or a wall-clock cap is exceeded, so that large sizes cannot destabilise the host.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

import torch

from fl_security.smpc import mp_spdz
from fl_security.smpc.fixed_point import FixedPointEncoder
from fl_security.smpc.robust import (
    SecureDefenceConfig,
    chunked_wire_values,
    decode_robust_output,
    robust_reference,
    round_arguments,
)


@dataclass
class BenchmarkCase:
    program: str            # "weighted_sum" or "robust_aggregate"
    dimension: int
    clients: int = 4
    mode: str = "clip_screen"
    threshold: str = "adaptive"
    repeat: int = 0
    parties: int = 3

    @property
    def label(self) -> str:
        variant = "sum" if self.program == "weighted_sum" else f"{self.mode}-{self.threshold}"
        return f"{variant}-d{self.dimension}-k{self.clients}-p{self.parties}-r{self.repeat}"


class Watchdog:
    def __init__(self, cap_seconds: float, min_available_gib: float = 3.0, min_disk_gib: float = 2.0):
        self.cap = cap_seconds
        self.min_available = min_available_gib * 1024 ** 3
        self.min_disk = min_disk_gib * 1024 ** 3
        self.peak_rss = 0
        self.reason = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self.started = time.monotonic()

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2)

    def _party_rss(self) -> int:
        total = 0
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if b"spdz2k-party.x" not in (proc / "cmdline").read_bytes():
                    continue
                for line in (proc / "status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1]) * 1024
            except (OSError, ValueError):
                continue
        return total

    def _monitor_resources(self):
        while not self._stop.wait(0.25):
            self.peak_rss = max(self.peak_rss, self._party_rss())
            try:
                available = 0
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemAvailable:"):
                        available = int(line.split()[1]) * 1024
                if available and available < self.min_available:
                    self.reason = "available memory below floor"
                elif shutil.disk_usage("/").free < self.min_disk:
                    self.reason = "free disk below floor"
                elif time.monotonic() - self.started > self.cap:
                    self.reason = f"wall-clock cap {self.cap:.0f} s exceeded"
            except OSError:
                pass
            if self.reason:
                subprocess.run(["pkill", "-f", "[s]pdz2k-party.x"], check=False)
                return


def compile_counts(case: BenchmarkCase, config: SecureDefenceConfig | None) -> dict:
    """Compile-only resource counts reported by MP-SPDZ for this exact circuit."""
    home = Path(os.environ["FL_MPSPDZ_HOME"])
    name = f"zz_bench_{uuid.uuid4().hex[:10]}"
    source_dir = Path(__file__).parent / "programs"
    target = home / "Programs" / "Source" / f"{name}.mpc"
    ids = list(range(case.clients))
    counts = [100] * case.clients
    if case.program == "weighted_sum":
        shutil.copyfile(source_dir / "spdz2k_weighted_sum.mpc", target)
        args = [",".join(map(str, ids)), ",".join(map(str, counts)), str(case.dimension + 1),
                str(case.clients), "20000"]
    else:
        weights = config.quantized_weights(counts)
        args = round_arguments(ids, counts, weights, case.dimension + 1, case.clients, 20000,
                               config.chunk_size, config.round_spec(weights))
        target.write_text("ROUND_ARGUMENTS = " + json.dumps(args) + "\n"
                          + (source_dir / "spdz2k_robust_aggregate.mpc").read_text(), encoding="utf-8")
        args = []
    started = time.perf_counter()
    result = subprocess.run([sys.executable, str(home / "compile.py"), "-R", "64", "-M", name, *args],
                            cwd=home, capture_output=True, text=True, timeout=600, check=False)
    elapsed = time.perf_counter() - started
    for path in list((home / "Programs" / "Bytecode").glob(f"{name}*")) + \
            list((home / "Programs" / "Schedules").glob(f"{name}*")) + [target]:
        path.unlink(missing_ok=True)
    output = result.stdout + result.stderr
    found = {"compile_seconds": round(elapsed, 3), "compile_returncode": result.returncode}
    for key, pattern in {
        "integer_triples": r"(\d+) integer triples", "integer_bits": r"(\d+) integer bits",
        "integer_opens": r"(\d+) integer opens", "integer_randoms": r"(\d+) integer randoms",
        "integer_dot_products": r"(\d+) integer dot products", "vm_rounds": r"(\d+) virtual machine rounds",
    }.items():
        match = re.search(pattern, output)
        found[key] = int(match.group(1)) if match else 0
    return found


def _synthetic_updates(case: BenchmarkCase, seed: int) -> list[torch.Tensor]:
    generator = torch.Generator().manual_seed(seed)
    updates = []
    for index in range(case.clients):
        vector = torch.randn(case.dimension, generator=generator, dtype=torch.float64)
        norm = 0.5 + 0.25 * index if index < case.clients - 1 else 6.0   # one oversized update
        updates.append(vector / vector.norm() * norm)
    return updates


def run_case(case: BenchmarkCase, cap_seconds: float, seed: int = 0) -> dict:
    parties = mp_spdz.load_party_configuration(case.parties)
    hosts = [p.client_host for p in parties]
    port = mp_spdz.client_port_base()
    credentials = os.environ["FL_MPSPDZ_CLIENT_CREDENTIALS_DIR"]
    home = os.environ["FL_MPSPDZ_HOME"]
    ids = list(range(case.clients))
    counts = [100] * case.clients
    updates = _synthetic_updates(case, seed)
    config = None
    record = {**asdict(case), "label": case.label, "status": "failed"}
    round_id = f"bench-{case.label}-{uuid.uuid4().hex[:12]}"
    timings = {}
    with Watchdog(cap_seconds) as watchdog:
        try:
            started = time.perf_counter()
            if case.program == "weighted_sum":
                encoder = FixedPointEncoder(1_000_000)
                mp_spdz.start_round(parties, round_id, ids, case.dimension + 1, counts, case.clients, port)
            else:
                config = SecureDefenceConfig(mode=case.mode, threshold=case.threshold, static_norm=1.0,
                                             min_norm=0.05, max_norm=4.0, clip_bits=8)
                weights = config.quantized_weights(counts)
                spec = config.round_spec(weights)
                mp_spdz.start_round(parties, round_id, ids, case.dimension + 1, counts, case.clients, port,
                                    program="robust_aggregate", weights=weights, robust_spec=spec,
                                    chunk_size=config.chunk_size)
            timings["start_seconds"] = time.perf_counter() - started
            submit_started = time.perf_counter()
            encoded_rows = []
            for cid, update in zip(ids, updates):
                if case.program == "weighted_sum":
                    state = {"w": update.to(torch.float32)}
                    mp_spdz.submit_client_update(state, counts[cid], cid, hosts=hosts, port_base=port,
                                                 credentials_dir=credentials, mp_spdz_home=home,
                                                 encoder=encoder, max_clients=case.clients)
                else:
                    encoded = [int(v) for v in torch.round(update * config.scale).to(torch.int64).tolist()]
                    encoded_rows.append(encoded)
                    mp_spdz.submit_wire_values(chunked_wire_values(counts[cid], encoded, config.chunk_size),
                                               cid, hosts=hosts, port_base=port, credentials_dir=credentials,
                                               mp_spdz_home=home, chunk_size=config.chunk_size)
            timings["client_input_seconds_total"] = time.perf_counter() - submit_started
            receive_started = time.perf_counter()
            if case.program == "weighted_sum":
                result = mp_spdz.receive_weighted_average(
                    {"w": torch.zeros(case.dimension)}, hosts=hosts, port_base=port, credentials_dir=credentials,
                    mp_spdz_home=home, output_client_id=case.clients, encoder=encoder,
                    expected_total_examples=sum(counts))
                expected = torch.stack([u.to(torch.float32).to(torch.float64) for u in updates]).mean(0)
                record["max_abs_error"] = float((result["w"].to(torch.float64) - expected).abs().max())
                record["error_reference"] = "plaintext float64 FedAvg"
            else:
                output = mp_spdz.receive_robust_result(
                    hosts=hosts, port_base=port, credentials_dir=credentials, mp_spdz_home=home,
                    output_client_id=case.clients, client_count=case.clients, dimension=case.dimension)
                reference = robust_reference(encoded_rows, weights, spec)
                record["bit_exact_vs_reference"] = bool(
                    output.totals == reference.totals and output.accepted == reference.accepted
                    and output.threshold_squared == reference.threshold_squared)
                decoded = decode_robust_output(output, weights, config)
                record["accepted"] = json.dumps(output.accepted)
                record["output_check_passed"] = decoded.output_check_passed
                record["error_reference"] = "exact integer reference (bit-exact)"
            timings["output_seconds"] = time.perf_counter() - receive_started
            finish_started = time.perf_counter()
            stats = mp_spdz.finish_round(parties, round_id)
            timings["finish_seconds"] = time.perf_counter() - finish_started
            timings["total_seconds"] = time.perf_counter() - started
            record["status"] = "completed"
            record["protocol_seconds_max"] = max(s.get("protocol_seconds", math.nan) for s in stats)
            record["party_data_sent_mb_sum"] = sum(s.get("party_data_sent_mb", 0.0) for s in stats)
            record["global_data_sent_mb"] = stats[0].get("global_data_sent_mb")
            record["party_rounds_max"] = max(s.get("party_rounds", 0) for s in stats)
        except BaseException as exc:
            record["error"] = repr(exc)[:500]
            if watchdog.reason:
                record["status"] = "aborted"
                record["abort_reason"] = watchdog.reason
            try:
                mp_spdz.abort_round(parties, round_id)
            except Exception:
                pass
            if isinstance(exc, KeyboardInterrupt):
                raise
        record.update({k: round(v, 3) for k, v in timings.items()})
        record["peak_party_rss_mib"] = round(watchdog.peak_rss / 1024 ** 2, 1)
    record.update(compile_counts(case, config))
    return record


def run_benchmarks(cases: list[BenchmarkCase], output_dir: Path, cap_seconds: float) -> list[dict]:
    from fl_security.smpc.local_demo import local_spdz2k_environment

    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "benchmark_results.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            item = json.loads(line)
            if item.get("status") == "completed":
                done.add(item["label"])
    records = []
    by_parties: dict[int, list[BenchmarkCase]] = {}
    for case in cases:
        by_parties.setdefault(case.parties, []).append(case)
    for parties, group in by_parties.items():
        max_clients = max(case.clients for case in group)
        with local_spdz2k_environment(parties, max_clients, keep_logs_in=output_dir / "raw_logs"):
            for case in group:
                if case.label in done:
                    continue
                print(f"[benchmark] {case.label}", flush=True)
                record = run_case(case, cap_seconds, seed=case.repeat)
                record["host_load_average"] = os.getloadavg()
                records.append(record)
                with results_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, default=str) + "\n")
                print(f"    -> {record['status']} total={record.get('total_seconds')} "
                      f"protocol={record.get('protocol_seconds_max')}", flush=True)
                if record["status"] == "aborted":
                    break
    _ = random
    return records
