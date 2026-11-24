"""Start local MP-SPDZ party-control services for an end-to-end demonstration."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from fl_security.federated.flower_simulation import run_flower_simulation
from fl_security.smpc.mp_spdz_party_service import serve_party


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _free_port_span(count: int, excluded: set[int] | None = None) -> int:
    excluded = excluded or set()
    for base in range(20_000, 60_000 - count):
        if any(port in excluded for port in range(base, base + count)):
            continue
        sockets = []
        try:
            for port in range(base, base + count):
                sock = socket.socket()
                sock.bind(("127.0.0.1", port))
                sockets.append(sock)
            return base
        except OSError:
            continue
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError(f"could not reserve a span of {count} local ports")


def _wait_healthy(url: str, process: mp.Process, timeout: float = 15.0) -> None:
    deadline, last_error = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        if not process.is_alive():
            raise RuntimeError("MP-SPDZ party service exited during startup")
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=1.0) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"MP-SPDZ party service did not become healthy: {last_error}")


def run_with_local_mp_spdz(config: dict) -> None:
    """Run the local demonstration with one SPDZ2k service per MPC party."""
    smpc = config.get("smpc", {})
    if not smpc.get("enabled", False):
        raise ValueError("local MP-SPDZ mode requires smpc.enabled=true")
    if smpc.get("backend") != "mp_spdz_spdz2k":
        raise ValueError("local MP-SPDZ mode requires backend=mp_spdz_spdz2k")
    party_count = int(smpc["num_aggregation_parties"])
    client_count = int(config["federated_learning"]["num_clients"])
    with local_spdz2k_environment(party_count, client_count):
        run_flower_simulation(config)


@contextmanager
def local_spdz2k_environment(party_count: int, client_count: int, *, keep_logs_in=None):
    """Start one authenticated SPDZ2k party service per party on this host.

    Inside the context the coordinator environment variables
    (FL_MPSPDZ_PARTIES_JSON, FL_MPSPDZ_CLIENT_PORT_BASE,
    FL_MPSPDZ_CLIENT_CREDENTIALS_DIR) point at the temporary deployment. Client
    IDs 0..client_count-1 and the output client ID ``client_count`` receive
    temporary TLS credentials. If ``keep_logs_in`` is a directory, party logs
    are copied there before the temporary deployment is removed.
    """
    mp_home_value = os.environ.get("FL_MPSPDZ_HOME")
    if not mp_home_value:
        raise RuntimeError("FL_MPSPDZ_HOME must point to the pinned MP-SPDZ v0.4.3 tree")
    mp_home = Path(mp_home_value).expanduser().resolve()
    if os.name != "posix":
        raise RuntimeError("local MP-SPDZ mode requires a Linux/POSIX host")
    if party_count < 2 or client_count < 1:
        raise ValueError("local SPDZ2k deployment requires two parties and one client")

    client_port = _free_port_span(party_count)
    player_port = _free_port_span(
        party_count, set(range(client_port, client_port + party_count))
    )
    context = mp.get_context("spawn")
    processes = []
    parties = {}
    runtime_root = Path(tempfile.mkdtemp(prefix="fl-mp-spdz-"))
    player_data = runtime_root / "Player-Data"
    player_data.mkdir()
    ip_file = runtime_root / "hosts"
    ip_file.write_text(
        "".join(
            f"127.0.0.1:{player_port + party_id}\n"
            for party_id in range(party_count)
        ),
        encoding="utf-8",
    )

    protected_names = (
        "FL_MPSPDZ_PARTIES_JSON",
        "FL_MPSPDZ_CLIENT_PORT_BASE",
        "FL_MPSPDZ_CLIENT_CREDENTIALS_DIR",
        "FL_MPSPDZ_CONTROL_TOKEN",
        "FL_MPSPDZ_HOME",
        "FL_SMPC_AGGREGATORS_JSON",
        "FL_SMPC_CLIENT_KEYS_JSON",
        "FL_SMPC_CLIENT_TOKENS_JSON",
        "FL_SMPC_CONTROL_TOKEN",
        "FL_MTD_SECRET",
    )
    previous_env = {
        name: os.environ.pop(name)
        for name in protected_names
        if name in os.environ
    }

    try:
        subprocess.run(
            [str(mp_home / "Scripts" / "setup-ssl.sh"), str(party_count), str(player_data)],
            cwd=runtime_root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [str(mp_home / "Scripts" / "setup-clients.sh"), str(client_count + 1)],
            cwd=runtime_root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for party_id in range(party_count):
            service_port = _free_port()
            service_url = f"http://127.0.0.1:{service_port}"
            control_token = secrets.token_urlsafe(32)
            work_dir = runtime_root / f"party-{party_id}"
            work_dir.mkdir()
            (work_dir / "Programs").symlink_to(
                mp_home / "Programs", target_is_directory=True
            )
            (work_dir / "Player-Data").symlink_to(
                player_data, target_is_directory=True
            )
            process = context.Process(
                target=serve_party,
                kwargs={
                    "host": "127.0.0.1",
                    "port": service_port,
                    "mp_spdz_home": str(mp_home),
                    "work_dir": str(work_dir),
                    "ip_file": str(ip_file),
                    "party_id": party_id,
                    "party_count": party_count,
                    "client_port_base": client_port,
                    "control_token": control_token,
                    # Early-crash detection window after launching spdz2k-party.x;
                    # later failures are still caught by status polling.
                    "startup_timeout": float(
                        os.environ.get("FL_MPSPDZ_STARTUP_TIMEOUT", "2.0")
                    ),
                },
                name=f"fl-mp-spdz-party-{party_id}",
            )
            process.start()
            processes.append(process)
            parties[str(party_id)] = {
                "control_url": service_url,
                "control_token": control_token,
                "client_host": "127.0.0.1",
            }

        for party_id, party in parties.items():
            _wait_healthy(
                party["control_url"],
                processes[int(party_id)],
            )

        os.environ["FL_MPSPDZ_HOME"] = str(mp_home)
        os.environ["FL_MPSPDZ_PARTIES_JSON"] = json.dumps(
            parties, separators=(",", ":")
        )
        os.environ["FL_MPSPDZ_CLIENT_PORT_BASE"] = str(client_port)
        os.environ["FL_MPSPDZ_CLIENT_CREDENTIALS_DIR"] = str(runtime_root)
        if "FL_MTD_SECRET" in previous_env:
            os.environ["FL_MTD_SECRET"] = previous_env["FL_MTD_SECRET"]
        yield {
            "runtime_root": runtime_root,
            "party_count": party_count,
            "client_port_base": client_port,
            "parties": parties,
        }
    finally:
        for name in protected_names:
            os.environ.pop(name, None)
        os.environ.update(previous_env)
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
        if keep_logs_in is not None:
            destination = Path(keep_logs_in)
            destination.mkdir(parents=True, exist_ok=True)
            for log in runtime_root.glob("party-*/logs/*.log"):
                shutil.copy2(log, destination / f"{log.parent.parent.name}_{log.name}")
        shutil.rmtree(runtime_root)
