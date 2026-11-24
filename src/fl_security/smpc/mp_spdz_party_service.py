"""Authenticated per-party process control for MP-SPDZ SPDZ2k rounds."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_CONTROL_BODY = 64 * 1024
CONTROL_CLOCK_SKEW_SECONDS = 300
ROUND_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WEIGHTED_SUM_PROGRAM = "weighted_sum"
ROBUST_PROGRAM = "robust_aggregate"
PROGRAM_SOURCES = {
    WEIGHTED_SUM_PROGRAM: "spdz2k_weighted_sum.mpc",
    ROBUST_PROGRAM: "spdz2k_robust_aggregate.mpc",
}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProgramIdentity:
    program_base: str
    program_name: str
    args: list[str]
    kind: str = WEIGHTED_SUM_PROGRAM

    def __iter__(self):
        """Backward-compatible ``base, name, args = identity`` unpacking."""
        return iter((self.program_base, self.program_name, self.args))


@dataclass
class RoundProcess:
    round_id: str
    program_base: str
    program_name: str
    process: subprocess.Popen
    log_path: Path
    log_file: object
    timeout: threading.Timer


class MPSpdzPartyService:
    def __init__(
        self,
        *,
        mp_spdz_home: str | os.PathLike[str],
        work_dir: str | os.PathLike[str],
        ip_file: str | os.PathLike[str],
        party_id: int,
        party_count: int,
        client_port_base: int,
        control_token: str,
        round_timeout: int = 600,
        startup_timeout: float = 2.0,
    ):
        self.mp_home = Path(mp_spdz_home).expanduser().resolve()
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.ip_file = Path(ip_file).expanduser().resolve()
        self.party_id = party_id
        self.party_count = party_count
        self.client_port_base = client_port_base
        self.control_token = control_token
        self.round_timeout = round_timeout
        self.startup_timeout = startup_timeout
        self.lock = threading.RLock()
        self.current: RoundProcess | None = None
        self.round_metadata: dict[str, tuple[str, str]] = {}
        self.seen_rounds_path = self.work_dir / "used-round-ids.jsonl"
        self.seen_round_ids = self._load_seen_round_ids()
        self.seen_control_requests_path = self.work_dir / "used-control-requests.jsonl"
        self.seen_control_requests = self._load_seen_control_requests()
        self._validate_installation()

    def _load_seen_round_ids(self) -> set[str]:
        if not self.seen_rounds_path.exists():
            return set()
        seen = set()
        for line in self.seen_rounds_path.read_text(encoding="utf-8").splitlines():
            if line:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"invalid round-ID journal: {self.seen_rounds_path}"
                    ) from exc
                if isinstance(value, str):
                    seen.add(value)
        return seen

    def _load_seen_control_requests(self) -> dict[str, int]:
        if not self.seen_control_requests_path.exists():
            return {}
        now = int(time.time())
        seen: dict[str, int] = {}
        for line in self.seen_control_requests_path.read_text(
            encoding="utf-8"
        ).splitlines():
            if not line:
                continue
            try:
                record = json.loads(line)
                request_id, timestamp = record["request_id"], record["timestamp"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise RuntimeError(
                    f"invalid control-request journal: {self.seen_control_requests_path}"
                ) from exc
            if (
                isinstance(request_id, str)
                and REQUEST_ID_PATTERN.fullmatch(request_id)
                and isinstance(timestamp, int)
                and abs(now - timestamp) <= CONTROL_CLOCK_SKEW_SECONDS
            ):
                seen[request_id] = timestamp
        self._write_control_request_journal(seen)
        return seen

    def _write_control_request_journal(self, requests: dict[str, int]) -> None:
        self.seen_control_requests_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.seen_control_requests_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as journal:
            for request_id, timestamp in requests.items():
                journal.write(
                    json.dumps(
                        {"request_id": request_id, "timestamp": timestamp},
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            journal.flush()
            os.fsync(journal.fileno())
        os.replace(temporary, self.seen_control_requests_path)

    def consume_control_request(self, request_id: str, timestamp: int) -> bool:
        with self.lock:
            now = int(time.time())
            self.seen_control_requests = {
                key: value
                for key, value in self.seen_control_requests.items()
                if abs(now - value) <= CONTROL_CLOCK_SKEW_SECONDS
            }
            if request_id in self.seen_control_requests:
                return False
            self.seen_control_requests[request_id] = timestamp
            self._write_control_request_journal(self.seen_control_requests)
            return True

    def _validate_installation(self) -> None:
        if os.name != "posix":
            raise RuntimeError("MP-SPDZ party service requires a Linux/POSIX host")
        if (
            isinstance(self.party_id, bool)
            or not isinstance(self.party_id, int)
            or isinstance(self.party_count, bool)
            or not isinstance(self.party_count, int)
        ):
            raise ValueError("party_id and party_count must be integers")
        if not (self.mp_home / "spdz2k-party.x").is_file():
            raise RuntimeError(f"spdz2k-party.x is missing from {self.mp_home}")
        if not (self.mp_home / "compile.py").is_file():
            raise RuntimeError(f"compile.py is missing from {self.mp_home}")
        if not self.ip_file.is_file():
            raise RuntimeError(f"MP-SPDZ IP file does not exist: {self.ip_file}")
        if not (self.work_dir / "Player-Data" / f"P{self.party_id}.pem").is_file():
            raise RuntimeError("party TLS certificate is missing from Player-Data")
        if not (self.work_dir / "Player-Data" / f"P{self.party_id}.key").is_file():
            raise RuntimeError("party TLS private key is missing from Player-Data")
        if not (self.work_dir / "Programs").exists():
            (self.work_dir / "Programs").symlink_to(
                self.mp_home / "Programs", target_is_directory=True
            )
        lines = [
            line.strip()
            for line in self.ip_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(lines) != self.party_count:
            raise ValueError(
                f"MP-SPDZ IP file must contain {self.party_count} party addresses"
            )
        if self.party_id < 0 or self.party_id >= self.party_count:
            raise ValueError("party_id is outside the configured party set")
        if self.party_count < 2:
            raise ValueError("SPDZ2k requires at least two parties")
        if not isinstance(self.control_token, str) or len(self.control_token) < 32:
            raise ValueError("control token must contain at least 32 characters")
        if (
            self.client_port_base < 1024
            or self.client_port_base + self.party_count - 1 > 65535
        ):
            raise ValueError("client port base is outside the valid TCP port range")
        if not 30 <= self.round_timeout <= 86_400:
            raise ValueError("round timeout must be between 30 and 86400 seconds")

    def _program_identity(self, round_id: str, payload: dict) -> ProgramIdentity:
        if not ROUND_ID_PATTERN.fullmatch(round_id):
            raise ValueError("round ID contains invalid characters")
        kind = payload.get("program", WEIGHTED_SUM_PROGRAM)
        if kind not in PROGRAM_SOURCES:
            raise ValueError("unsupported SPDZ2k program")
        allowed = {
            "client_ids", "input_count", "expected_counts", "output_client_id",
            "client_port_base", "program",
        }
        if kind == ROBUST_PROGRAM:
            allowed |= {"weights", "robust_spec", "chunk_size", "direction"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unexpected SPDZ2k round fields: {sorted(unknown)}")
        clients = payload.get("client_ids")
        input_count = payload.get("input_count")
        expected_counts = payload.get("expected_counts")
        output_client_id = payload.get("output_client_id")
        port_base = payload.get("client_port_base")
        if not isinstance(clients, list) or not clients:
            raise ValueError("client_ids must be a non-empty list")
        if any(isinstance(cid, bool) or not isinstance(cid, int) or cid < 0 for cid in clients):
            raise ValueError("client_ids must contain non-negative integers")
        if len(set(clients)) != len(clients):
            raise ValueError("client_ids must be unique")
        if (
            isinstance(input_count, bool)
            or not isinstance(input_count, int)
            or input_count <= 0
        ):
            raise ValueError("input_count must be a positive integer")
        if (
            not isinstance(expected_counts, list)
            or len(expected_counts) != len(clients)
            or any(
                isinstance(count, bool) or not isinstance(count, int) or count <= 0
                for count in expected_counts
            )
        ):
            raise ValueError("expected_counts must contain one positive server-known count per client")
        if (
            isinstance(output_client_id, bool)
            or not isinstance(output_client_id, int)
            or output_client_id < 0
            or output_client_id in clients
        ):
            raise ValueError("output_client_id must be distinct from all input clients")
        if port_base != self.client_port_base:
            raise ValueError("client port base does not match party configuration")
        if max(clients + [output_client_id]) > 65_535:
            raise ValueError("client IDs must not exceed 65535")

        program_base = "fl_spdz_" + hashlib.sha256(round_id.encode()).hexdigest()[:20]
        if kind == ROBUST_PROGRAM:
            from fl_security.smpc.robust import round_arguments, validate_spec

            weights = payload.get("weights")
            spec = payload.get("robust_spec")
            chunk_size = payload.get("chunk_size")
            if (
                not isinstance(weights, list)
                or len(weights) != len(clients)
                or any(isinstance(w, bool) or not isinstance(w, int) or not 0 < w <= 65_535 for w in weights)
            ):
                raise ValueError("weights must contain one positive integer per client")
            if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or not 16 <= chunk_size <= 4096:
                raise ValueError("chunk_size must be an integer in [16, 4096]")
            if not isinstance(spec, list):
                raise ValueError("robust_spec must be a list of integers")
            if len(clients) < 2 or input_count < 2:
                raise ValueError("robust aggregation requires two clients and one parameter")
            validate_spec(spec, weights)
            # the optional direction screen is validated inside round_arguments
            args = round_arguments(
                clients, expected_counts, weights, input_count,
                output_client_id, port_base, chunk_size, spec,
                direction=payload.get("direction"),
            )
            return ProgramIdentity(program_base, program_base, args, ROBUST_PROGRAM)

        args = [
            ",".join(str(client_id) for client_id in sorted(clients)),
            ",".join(str(count) for _, count in sorted(zip(clients, expected_counts))),
            str(input_count),
            str(output_client_id),
            str(port_base),
        ]
        program_name = program_base + "-" + "-".join(args)
        return ProgramIdentity(program_base, program_name, args, WEIGHTED_SUM_PROGRAM)

    def _compile(self, identity: ProgramIdentity) -> str:
        if sys.platform != "linux":
            raise RuntimeError("SPDZ2k circuit compilation requires Linux")
        import fcntl

        program_base, program_name = identity.program_base, identity.program_name
        lock_path = self.mp_home / ".fl-spdz2k-compile.lock"
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            source = Path(__file__).parent / "programs" / PROGRAM_SOURCES[identity.kind]
            target = self.mp_home / "Programs" / "Source" / f"{program_base}.mpc"
            if identity.kind == ROBUST_PROGRAM:
                # Arguments were validated above and contain only digits and commas;
                # embedding them keeps the bytecode name short and hash-bound.
                header = "ROUND_ARGUMENTS = " + json.dumps(identity.args) + "\n"
                target.write_text(header + source.read_text(encoding="utf-8"), encoding="utf-8")
                compile_args: list[str] = []
            else:
                shutil.copyfile(source, target)
                compile_args = list(identity.args)
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(self.mp_home / "compile.py"),
                        "-R",
                        "64",
                        # Preserve MP-SPDZ memory-instruction order for indirect
                        # Array accesses used by chunked aggregation (compiler -M).
                        "-M",
                        program_base,
                        *compile_args,
                    ],
                    cwd=self.mp_home,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("SPDZ2k circuit compilation timed out") from exc
            if result.returncode != 0:
                detail = (result.stdout + "\n" + result.stderr)[-4000:]
                raise RuntimeError(f"SPDZ2k circuit compilation failed: {detail}")
            bytecode = (
                self.mp_home
                / "Programs"
                / "Bytecode"
                / f"{program_name}-0.bc"
            )
            if not bytecode.is_file():
                raise RuntimeError("SPDZ2k compiler did not produce expected bytecode")
            return hashlib.sha256(bytecode.read_bytes()).hexdigest()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def start(self, round_id: str, payload: dict) -> dict:
        with self.lock:
            if self.current is not None:
                raise RuntimeError("this SPDZ2k party already has an active round")
            if round_id in self.seen_round_ids:
                raise RuntimeError("SPDZ2k round ID has already been used")
            identity = self._program_identity(round_id, payload)
            program_base, program_name = identity.program_base, identity.program_name
            self.round_metadata[round_id] = (program_base, program_name)
            self.seen_rounds_path.parent.mkdir(parents=True, exist_ok=True)
            with self.seen_rounds_path.open("a", encoding="utf-8") as journal:
                journal.write(json.dumps(round_id) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
            self.seen_round_ids.add(round_id)

            program_hash = self._compile(identity)
            log_dir = self.work_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{program_base}-P{self.party_id}.log"
            log_file = log_path.open("wb")
            env = dict(os.environ)
            existing_ld_path = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = os.pathsep.join(
                item for item in (str(self.mp_home), existing_ld_path) if item
            )
            command = [
                str(self.mp_home / "spdz2k-party.x"),
                "-p",
                str(self.party_id),
                "-N",
                str(self.party_count),
                "-ip",
                str(self.ip_file),
                "-e",
                program_name,
            ]
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.work_dir,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
            except OSError:
                log_file.close()
                raise

            timeout = threading.Timer(
                self.round_timeout, self._timeout_round, args=(round_id,)
            )
            timeout.daemon = True
            self.current = RoundProcess(
                round_id=round_id,
                program_base=program_base,
                program_name=program_name,
                process=process,
                log_path=log_path,
                log_file=log_file,
                timeout=timeout,
            )
            timeout.start()
            deadline = time.monotonic() + self.startup_timeout
            while time.monotonic() < deadline:
                exit_code = process.poll()
                if exit_code is not None:
                    detail = self._read_log_tail(log_path)
                    self._close_current()
                    raise RuntimeError(
                        f"SPDZ2k party process exited during startup ({exit_code}): {detail}"
                    )
                time.sleep(0.05)
            return {"status": "running", "program_sha256": program_hash}

    @staticmethod
    def _protocol_statistics(text: str) -> dict:
        """Parse MP-SPDZ's end-of-run summary (measured by the party binary)."""
        stats: dict[str, float] = {}
        patterns = {
            "protocol_seconds": r"^Time = ([0-9.eE+-]+) seconds",
            "party_data_sent_mb": r"^Data sent = ([0-9.eE+-]+) MB",
            "party_rounds": r"^Data sent = [0-9.eE+-]+ MB in ~([0-9]+) rounds",
            "global_data_sent_mb": r"^Global data sent = ([0-9.eE+-]+) MB",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text, flags=re.MULTILINE)
            if match:
                stats[key] = float(match.group(1))
        return stats

    def _read_log_tail(self, path: Path) -> str:
        try:
            with path.open("rb") as log:
                log.seek(max(0, path.stat().st_size - 4000))
                return log.read().decode("utf-8", errors="replace")
        except OSError as exc:
            return f"unable to read party log: {exc}"

    def _close_current(self) -> None:
        if self.current is None:
            return
        self.current.timeout.cancel()
        self.current.log_file.close()
        self.current = None

    def _timeout_round(self, round_id: str) -> None:
        with self.lock:
            current = self.current
            if current is None or current.round_id != round_id:
                return
            if current.process.poll() is None:
                logger.error("SPDZ2k round %s exceeded its timeout", round_id)
                current.process.terminate()
                try:
                    current.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    current.process.kill()
                    current.process.wait(timeout=5)

    def status(self, round_id: str) -> dict:
        with self.lock:
            current = self.current
            if current is None or current.round_id != round_id:
                raise RuntimeError("SPDZ2k round is not active on this party")
            exit_code = current.process.poll()
            if exit_code is None:
                return {"status": "running"}
            current.timeout.cancel()
            current.log_file.flush()
            if exit_code == 0:
                return {
                    "status": "completed",
                    "exit_code": 0,
                    "statistics": self._protocol_statistics(
                        self._read_log_tail(current.log_path)
                    ),
                }
            return {
                "status": "failed",
                "exit_code": exit_code,
                "error": self._read_log_tail(current.log_path),
            }

    def stop(self, round_id: str) -> dict:
        with self.lock:
            current = self.current
            if current is None:
                return {"status": "stopped"}
            if current.round_id != round_id:
                raise RuntimeError("requested round does not match active SPDZ2k round")
            if current.process.poll() is None:
                current.process.terminate()
                try:
                    current.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    current.process.kill()
                    current.process.wait(timeout=5)
            current.timeout.cancel()
            current.log_file.flush()
            return {"status": "stopped"}

    def cleanup(self, round_id: str) -> dict:
        with self.lock:
            current = self.current
            metadata = self.round_metadata.get(round_id)
            if metadata is None:
                return {"status": "cleaned"}
            if current is not None and current.round_id != round_id:
                raise RuntimeError("requested round does not match active SPDZ2k round")
            if current is not None and current.process.poll() is None:
                raise RuntimeError("cannot clean up a running SPDZ2k party process")
            if current is not None:
                current.timeout.cancel()
                current.log_file.close()
                self.current = None
            program_base, program_name = metadata
            (self.mp_home / "Programs" / "Source" / f"{program_base}.mpc").unlink(
                missing_ok=True
            )
            (self.mp_home / "Programs" / "Schedules" / f"{program_name}.sch").unlink(
                missing_ok=True
            )
            # Remove the main tape and every auxiliary tape of this round (for
            # example EQZ/LTZ function tapes); earlier versions removed only -0.bc.
            bytecode_dir = self.mp_home / "Programs" / "Bytecode"
            prefix = f"{program_name}-"
            for tape in bytecode_dir.iterdir() if bytecode_dir.is_dir() else []:
                if tape.name.startswith(prefix) and tape.name.endswith(".bc"):
                    tape.unlink(missing_ok=True)
            del self.round_metadata[round_id]
            return {"status": "cleaned"}


def create_handler(service: MPSpdzPartyService):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.info("MPC control %s - %s", self.address_string(), fmt % args)

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlsplit(self.path).path == "/health":
                self._send(200, {"status": "ok", "party_id": service.party_id})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            parsed_path = urlsplit(self.path)
            route = parsed_path.path
            match = re.fullmatch(
                r"/v1/rounds/([A-Za-z0-9_.-]{1,128})/(start|status|stop|cleanup)",
                route,
            )
            if match is None or parsed_path.query or parsed_path.fragment:
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, {"error": "invalid content length"})
                return
            if length < 0 or length > MAX_CONTROL_BODY:
                self._send(413, {"error": "request body is too large"})
                return
            body = self.rfile.read(length)
            timestamp_raw = self.headers.get("X-Timestamp", "")
            request_id = self.headers.get("X-Request-ID", "")
            if not timestamp_raw.isdecimal() or not REQUEST_ID_PATTERN.fullmatch(
                request_id
            ):
                self._send(401, {"error": "invalid control request metadata"})
                return
            timestamp = int(timestamp_raw)
            if abs(int(time.time()) - timestamp) > CONTROL_CLOCK_SKEW_SECONDS:
                self._send(401, {"error": "control request timestamp is outside the allowed window"})
                return
            expected = hmac.new(
                service.control_token.encode(),
                b"POST\n"
                + route.encode()
                + b"\n"
                + timestamp_raw.encode()
                + b"\n"
                + request_id.encode()
                + b"\n"
                + body,
                hashlib.sha256,
            ).hexdigest()
            provided = self.headers.get("X-Signature", "")
            if not hmac.compare_digest(expected, provided):
                self._send(401, {"error": "invalid control signature"})
                return
            if not service.consume_control_request(request_id, timestamp):
                self._send(409, {"error": "replayed control request"})
                return
            try:
                payload = json.loads(body or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                round_id, action = match.groups()
                if action == "start":
                    response = service.start(round_id, payload)
                elif action == "status":
                    response = service.status(round_id)
                elif action == "stop":
                    response = service.stop(round_id)
                else:
                    response = service.cleanup(round_id)
                self._send(200, response)
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})
            except RuntimeError as exc:
                self._send(409, {"error": str(exc)})
            except Exception:
                logger.exception("SPDZ2k control request failed")
                self._send(500, {"error": "internal SPDZ2k party service error"})

    return Handler


def serve_party(
    host: str,
    port: int,
    *,
    mp_spdz_home: str | os.PathLike[str],
    work_dir: str | os.PathLike[str],
    ip_file: str | os.PathLike[str],
    party_id: int,
    party_count: int,
    client_port_base: int,
    control_token: str,
    round_timeout: int = 600,
    startup_timeout: float = 2.0,
) -> None:
    if not 0.1 <= float(startup_timeout) <= 30.0:
        raise ValueError("startup_timeout must be between 0.1 and 30 seconds")
    service = MPSpdzPartyService(
        mp_spdz_home=mp_spdz_home,
        work_dir=work_dir,
        ip_file=ip_file,
        party_id=party_id,
        party_count=party_count,
        client_port_base=client_port_base,
        control_token=control_token,
        round_timeout=round_timeout,
        startup_timeout=float(startup_timeout),
    )

    def handle_shutdown(signum, frame):
        del signum, frame
        current = service.current
        if current is not None:
            service.stop(current.round_id)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    server = ThreadingHTTPServer((host, port), create_handler(service))
    server.serve_forever()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run an MP-SPDZ SPDZ2k party service")
    parser.add_argument("--host", default=os.environ.get("FL_MPSPDZ_SERVICE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FL_MPSPDZ_SERVICE_PORT", "8710")))
    args = parser.parse_args()
    serve_party(
        args.host,
        args.port,
        mp_spdz_home=os.environ["FL_MPSPDZ_HOME"],
        work_dir=os.environ["FL_MPSPDZ_WORK_DIR"],
        ip_file=os.environ["FL_MPSPDZ_IP_FILE"],
        party_id=int(os.environ["FL_MPSPDZ_PARTY_ID"]),
        party_count=int(os.environ["FL_MPSPDZ_PARTY_COUNT"]),
        client_port_base=int(os.environ["FL_MPSPDZ_CLIENT_PORT_BASE"]),
        control_token=os.environ["FL_MPSPDZ_CONTROL_TOKEN"],
        round_timeout=int(os.environ.get("FL_MPSPDZ_ROUND_TIMEOUT", "600")),
    )


if __name__ == "__main__":
    main()
