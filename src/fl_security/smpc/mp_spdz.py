"""Client and control-plane helpers for the pinned MP-SPDZ SPDZ2k backend."""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import torch

from fl_security.smpc.fixed_point import FixedPointEncoder
from fl_security.smpc.transport import urlopen_secure, validate_transport_url

SPDZ2K_BACKEND = "mp_spdz_spdz2k"
SPDZ2K_RING_BITS = 64
SPDZ2K_IO_CHUNK_SIZE = 1024
CLIENT_IO_TIMEOUT_SECONDS = 600.0
_CLIENT_IMPORT_LOCK = threading.RLock()
_CLIENT_CWD_LOCK = threading.RLock()


@dataclass(frozen=True)
class MPSpdzParty:
    party_id: int
    control_url: str
    control_token: str
    client_host: str


def load_party_configuration(num_parties: int) -> list[MPSpdzParty]:
    if isinstance(num_parties, bool) or not isinstance(num_parties, int) or num_parties < 2:
        raise ValueError("SPDZ2k requires at least two parties")
    raw = os.environ.get("FL_MPSPDZ_PARTIES_JSON", "")
    if not raw:
        raise RuntimeError("FL_MPSPDZ_PARTIES_JSON is required for SPDZ2k")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("FL_MPSPDZ_PARTIES_JSON must contain valid JSON") from exc
    if not isinstance(config, dict):
        raise ValueError("FL_MPSPDZ_PARTIES_JSON must be an object keyed by party ID")
    expected_ids = {str(party_id) for party_id in range(num_parties)}
    if set(config) != expected_ids:
        raise ValueError(
            "FL_MPSPDZ_PARTIES_JSON must configure every SPDZ2k party exactly once"
        )

    parties = []
    for party_id in range(num_parties):
        item = config[str(party_id)]
        if not isinstance(item, dict):
            raise ValueError(f"SPDZ2k party {party_id} configuration must be an object")
        control_url = item.get("control_url")
        control_token = item.get("control_token")
        client_host = item.get("client_host")
        if not isinstance(control_url, str) or not isinstance(client_host, str):
            raise ValueError(
                f"SPDZ2k party {party_id} requires string control_url and client_host values"
            )
        control_url = control_url.rstrip("/")
        client_host = client_host.strip()
        if not isinstance(control_token, str) or len(control_token) < 32:
            raise ValueError(
                f"SPDZ2k party {party_id} requires a control token of at least 32 characters"
            )
        if not client_host:
            raise ValueError(f"SPDZ2k party {party_id} requires client_host")
        validate_transport_url(control_url)
        parties.append(
            MPSpdzParty(
                party_id=party_id,
                control_url=control_url,
                control_token=control_token,
                client_host=client_host,
            )
        )
    if len({party.control_token for party in parties}) != len(parties):
        raise ValueError("each SPDZ2k party must have a unique control token")
    if len({party.control_url for party in parties}) != len(parties):
        raise ValueError("each SPDZ2k party must have a unique control URL")
    return parties


def client_port_base() -> int:
    raw = os.environ.get("FL_MPSPDZ_CLIENT_PORT_BASE", "")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("FL_MPSPDZ_CLIENT_PORT_BASE must be configured") from exc
    if value < 1024 or value > 65535:
        raise ValueError("FL_MPSPDZ_CLIENT_PORT_BASE must be a valid TCP port base")
    return value


def _load_external_io_client_class(mp_spdz_home: str | os.PathLike[str]):
    external_io = Path(mp_spdz_home).expanduser().resolve() / "ExternalIO"
    client_path, domains_path = external_io / "client.py", external_io / "domains.py"
    if not client_path.is_file() or not domains_path.is_file():
        raise RuntimeError(
            f"MP-SPDZ ExternalIO client files were not found under {external_io}"
        )
    module_suffix = hashlib.sha256(str(external_io).encode()).hexdigest()[:12]
    client_module_name = f"_fl_mp_spdz_client_{module_suffix}"
    domains_module_name = f"_fl_mp_spdz_domains_{module_suffix}"

    with _CLIENT_IMPORT_LOCK:
        cached = sys.modules.get(client_module_name)
        if cached is not None:
            return cached.Client

        domains_spec = importlib.util.spec_from_file_location(
            domains_module_name, domains_path
        )
        if domains_spec is None or domains_spec.loader is None:
            raise RuntimeError("could not load the MP-SPDZ external client domains module")
        domains_module = importlib.util.module_from_spec(domains_spec)
        previous_domains = sys.modules.get("domains")
        sys.modules[domains_module_name] = domains_module
        sys.modules["domains"] = domains_module
        try:
            domains_spec.loader.exec_module(domains_module)
            client_spec = importlib.util.spec_from_file_location(
                client_module_name, client_path
            )
            if client_spec is None or client_spec.loader is None:
                raise RuntimeError("could not load the MP-SPDZ external client module")
            client_module = importlib.util.module_from_spec(client_spec)
            sys.modules[client_module_name] = client_module
            client_spec.loader.exec_module(client_module)
        finally:
            if previous_domains is None:
                sys.modules.pop("domains", None)
            else:
                sys.modules["domains"] = previous_domains
        return client_module.Client


def _connect_client(
    client_class,
    hosts: Sequence[str],
    port_base: int,
    client_id: int,
    credentials_dir: str | os.PathLike[str],
):
    directory = Path(credentials_dir).expanduser().resolve()
    if not directory.is_dir():
        raise RuntimeError(f"MP-SPDZ client credential directory does not exist: {directory}")
    with _CLIENT_CWD_LOCK:
        previous_directory = os.getcwd()
        client = None
        try:
            os.chdir(directory)
            client = client_class(list(hosts), port_base, client_id)
            for connection in client.sockets:
                connection.settimeout(CLIENT_IO_TIMEOUT_SECONDS)
            return client
        except Exception as error:
            if client is not None:
                for connection in client.sockets:
                    try:
                        connection.close()
                    except OSError as close_error:
                        error.add_note(
                            f"SPDZ2k socket cleanup also failed: {close_error}"
                        )
            raise
        finally:
            os.chdir(previous_directory)


def _close_client(client) -> None:
    errors = []
    for connection in client.sockets:
        try:
            connection.close()
        except OSError as exc:
            errors.append(str(exc))
    if errors:
        raise RuntimeError("MP-SPDZ client socket cleanup failed: " + "; ".join(errors))


def _encode_weighted_model(
    state: Mapping[str, torch.Tensor],
    num_examples: int,
    encoder: FixedPointEncoder,
    max_clients: int,
) -> tuple[list[int], list[tuple[str, tuple[int, ...]]]]:
    if isinstance(num_examples, bool) or not isinstance(num_examples, int) or num_examples <= 0:
        raise ValueError("num_examples must be a positive integer")
    if (
        isinstance(max_clients, bool)
        or not isinstance(max_clients, int)
        or max_clients <= 0
        or max_clients > 65_535
    ):
        raise ValueError("max_clients must be an integer in [1, 65535]")

    values: list[int] = []
    layout: list[tuple[str, tuple[int, ...]]] = []
    ring_limit = (1 << (SPDZ2K_RING_BITS - 2)) // max_clients
    for key, tensor in state.items():
        if not torch.is_floating_point(tensor):
            continue
        weighted = tensor.detach().cpu().to(torch.float64) * num_examples
        encoded = encoder.encode(weighted)
        if encoded.numel() and int(encoded.abs().max().item()) >= ring_limit:
            raise OverflowError(
                f"weighted model tensor {key!r} exceeds the safe SPDZ2k ring range"
            )
        values.extend(int(value) for value in encoded.reshape(-1).tolist())
        layout.append((key, tuple(tensor.shape)))
    if not values:
        raise ValueError("model state contains no floating-point parameters")
    values.append(num_examples)
    return values, layout


def _prepare_chunked_client_inputs(
    encoded_values: Sequence[int], chunk_size: int = SPDZ2K_IO_CHUNK_SIZE
) -> list[int]:
    """Put the private sample count first and pad the vector to fixed I/O chunks."""
    if not encoded_values or isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("encoded_values and a positive chunk_size are required")
    count = encoded_values[-1]
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("encoded sample count must be a positive integer")
    wire_values = [count, *encoded_values[:-1]]
    wire_values.extend([0] * (-len(wire_values) % chunk_size))
    return wire_values


def submit_client_update(
    state: Mapping[str, torch.Tensor],
    num_examples: int,
    client_id: int,
    *,
    hosts: Sequence[str],
    port_base: int,
    credentials_dir: str | os.PathLike[str],
    mp_spdz_home: str | os.PathLike[str],
    encoder: FixedPointEncoder,
    max_clients: int,
) -> int:
    """Submit one authenticated private input to every configured MPC party."""
    values, _ = _encode_weighted_model(state, num_examples, encoder, max_clients)
    wire_values = _prepare_chunked_client_inputs(values)
    if (
        isinstance(client_id, bool)
        or not isinstance(client_id, int)
        or client_id < 0
        or client_id > 65_535
    ):
        raise ValueError("client_id must be a valid MP-SPDZ client ID")
    if len(hosts) < 2 or not all(isinstance(host, str) and host for host in hosts):
        raise ValueError("at least two SPDZ2k party hosts are required")
    client_class = _load_external_io_client_class(mp_spdz_home)
    client = _connect_client(
        client_class, hosts, port_base, client_id, credentials_dir
    )
    try:
        for offset in range(0, len(wire_values), SPDZ2K_IO_CHUNK_SIZE):
            client.send_private_inputs(
                wire_values[offset : offset + SPDZ2K_IO_CHUNK_SIZE]
            )
    finally:
        _close_client(client)
    return len(wire_values) * 8


def submit_client_delta(
    local_state: Mapping[str, torch.Tensor],
    global_state: Mapping[str, torch.Tensor],
    num_examples: int,
    client_id: int,
    *,
    hosts: Sequence[str],
    port_base: int,
    credentials_dir: str | os.PathLike[str],
    mp_spdz_home: str | os.PathLike[str],
    fractional_bits: int,
    chunk_size: int,
) -> int:
    """Submit ``[count, round((w_local - w_global) * 2^f)...]`` for robust aggregation."""
    from fl_security.smpc.robust import chunked_wire_values, encode_delta

    if (
        isinstance(client_id, bool)
        or not isinstance(client_id, int)
        or client_id < 0
        or client_id > 65_535
    ):
        raise ValueError("client_id must be a valid MP-SPDZ client ID")
    if len(hosts) < 2 or not all(isinstance(host, str) and host for host in hosts):
        raise ValueError("at least two SPDZ2k party hosts are required")
    encoded = encode_delta(local_state, global_state, fractional_bits)
    wire_values = chunked_wire_values(num_examples, encoded, chunk_size)
    client_class = _load_external_io_client_class(mp_spdz_home)
    client = _connect_client(client_class, hosts, port_base, client_id, credentials_dir)
    try:
        for offset in range(0, len(wire_values), chunk_size):
            client.send_private_inputs(wire_values[offset : offset + chunk_size])
    finally:
        _close_client(client)
    return len(wire_values) * 8


def receive_robust_result(
    *,
    hosts: Sequence[str],
    port_base: int,
    credentials_dir: str | os.PathLike[str],
    mp_spdz_home: str | os.PathLike[str],
    output_client_id: int,
    client_count: int,
    dimension: int,
    direction: bool = False,
):
    """Receive the robust program's header and weighted sum as the output client."""
    from fl_security.smpc.robust import result_from_outputs

    if (
        isinstance(output_client_id, bool)
        or not isinstance(output_client_id, int)
        or not 0 <= output_client_id <= 65_535
    ):
        raise ValueError("output_client_id must be a valid MP-SPDZ client ID")
    if client_count < 2 or dimension < 1:
        raise ValueError("robust output requires two clients and a positive dimension")
    client_class = _load_external_io_client_class(mp_spdz_home)
    client = _connect_client(client_class, hosts, port_base, output_client_id, credentials_dir)
    try:
        outputs = client.receive_outputs(
            2 + (3 if direction else 2) * client_count + dimension)
    finally:
        _close_client(client)
    return result_from_outputs(outputs, client_count, dimension, direction=direction)


def receive_weighted_average(
    global_state: Mapping[str, torch.Tensor],
    *,
    hosts: Sequence[str],
    port_base: int,
    credentials_dir: str | os.PathLike[str],
    mp_spdz_home: str | os.PathLike[str],
    output_client_id: int,
    encoder: FixedPointEncoder,
    expected_total_examples: int | None = None,
) -> dict[str, torch.Tensor]:
    """Receive the global weighted sum and sample count from the MPC output client."""
    output_count = sum(
        tensor.numel()
        for tensor in global_state.values()
        if torch.is_floating_point(tensor)
    )
    if output_count <= 0:
        raise ValueError("global model state contains no floating-point parameters")
    if (
        isinstance(output_client_id, bool)
        or not isinstance(output_client_id, int)
        or output_client_id < 0
        or output_client_id > 65_535
    ):
        raise ValueError("output_client_id must be a valid MP-SPDZ client ID")
    if len(hosts) < 2 or not all(isinstance(host, str) and host for host in hosts):
        raise ValueError("at least two SPDZ2k party hosts are required")
    client_class = _load_external_io_client_class(mp_spdz_home)
    client = _connect_client(
        client_class,
        hosts,
        port_base,
        output_client_id,
        credentials_dir,
    )
    padded_output_count = (
        (output_count + 1 + SPDZ2K_IO_CHUNK_SIZE - 1)
        // SPDZ2K_IO_CHUNK_SIZE
        * SPDZ2K_IO_CHUNK_SIZE
    )
    try:
        # Array.reveal_to_clients writes one contiguous output message. Input
        # submission is chunked, but the corresponding client read must match
        # the full revealed vector length in one receive_outputs() call.
        outputs = client.receive_outputs(padded_output_count)
    finally:
        _close_client(client)

    if len(outputs) != padded_output_count:
        raise RuntimeError("SPDZ2k output length did not match the padded model schema")
    total_examples = int(outputs[0])
    if total_examples <= 0:
        raise RuntimeError("SPDZ2k returned an invalid aggregate sample count")
    if (
        expected_total_examples is not None
        and total_examples != expected_total_examples
    ):
        raise RuntimeError(
            "SPDZ2k aggregate sample count did not match the successful client set"
        )

    if any(outputs[output_count + 1 :]):
        raise RuntimeError("SPDZ2k returned nonzero values in the padded output tail")
    result: dict[str, torch.Tensor] = {}
    offset = 1
    for key, base in global_state.items():
        if not torch.is_floating_point(base):
            result[key] = base.detach().clone()
            continue
        count = base.numel()
        weighted = torch.tensor(
            outputs[offset : offset + count], dtype=torch.float64
        ).reshape(base.shape)
        result[key] = (
            weighted / encoder.scale / total_examples
        ).to(device=base.device, dtype=base.dtype)
        offset += count
    if offset != output_count + 1:
        raise RuntimeError("SPDZ2k output length did not match the model schema")
    return result


def _control_request(
    party: MPSpdzParty,
    round_id: str,
    action: str,
    payload: Mapping[str, object] | None = None,
    timeout: float = 600.0,
) -> dict:
    route = f"/v1/rounds/{round_id}/{action}"
    body = json.dumps(
        dict(payload or {}), sort_keys=True, separators=(",", ":")
    ).encode()
    timestamp = str(int(time.time()))
    request_id = secrets.token_hex(32)
    signed = (
        b"POST\n"
        + route.encode()
        + b"\n"
        + timestamp.encode()
        + b"\n"
        + request_id.encode()
        + b"\n"
        + body
    )
    signature = hmac.new(
        party.control_token.encode(), signed, hashlib.sha256
    ).hexdigest()
    request = urllib.request.Request(
        party.control_url + route,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Request-ID": request_id,
            "X-Signature": signature,
        },
        method="POST",
    )
    try:
        with urlopen_secure(request, timeout=timeout) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"SPDZ2k party {party.party_id} {action} failed: {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"SPDZ2k party {party.party_id} {action} failed: {exc}"
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"SPDZ2k party {party.party_id} returned invalid JSON")
    return result


def start_round(
    parties: Sequence[MPSpdzParty],
    round_id: str,
    client_ids: Sequence[int],
    input_count: int,
    expected_counts: Sequence[int],
    output_client_id: int,
    port_base: int,
    *,
    program: str = "weighted_sum",
    weights: Sequence[int] | None = None,
    robust_spec: Sequence[int] | None = None,
    chunk_size: int | None = None,
    direction: Mapping[str, object] | None = None,
) -> None:
    if program not in ("weighted_sum", "robust_aggregate"):
        raise ValueError("unsupported SPDZ2k program")
    if not parties:
        raise ValueError("at least two SPDZ2k parties are required")
    if len(parties) < 2:
        raise ValueError("SPDZ2k requires at least two parties")
    if any(
        isinstance(client_id, bool)
        or not isinstance(client_id, int)
        or client_id < 0
        or client_id > 65_535
        for client_id in client_ids
    ):
        raise ValueError("client_ids must contain valid MP-SPDZ client IDs")
    clients = sorted(set(client_ids))
    if not clients or len(clients) != len(client_ids):
        raise ValueError("client_ids must be non-empty and unique")
    if (
        isinstance(input_count, bool)
        or not isinstance(input_count, int)
        or input_count <= 0
        or len(expected_counts) != len(clients)
        or any(
            isinstance(count, bool) or not isinstance(count, int) or count <= 0
            for count in expected_counts
        )
        or isinstance(output_client_id, bool)
        or not isinstance(output_client_id, int)
        or output_client_id < 0
        or output_client_id > 65_535
        or output_client_id in clients
    ):
        raise ValueError("invalid SPDZ2k round input or output client ID")
    if (
        isinstance(port_base, bool)
        or not isinstance(port_base, int)
        or port_base < 1024
        or port_base + len(parties) - 1 > 65_535
    ):
        raise ValueError("SPDZ2k client port range is invalid")
    client_count_pairs = sorted(zip(client_ids, expected_counts))
    payload = {
        "client_ids": [client_id for client_id, _ in client_count_pairs],
        "input_count": int(input_count),
        "expected_counts": [int(count) for _, count in client_count_pairs],
        "output_client_id": int(output_client_id),
        "client_port_base": int(port_base),
    }
    if program == "robust_aggregate":
        from fl_security.smpc.robust import validate_spec

        if weights is None or robust_spec is None or chunk_size is None:
            raise ValueError("robust aggregation requires weights, robust_spec and chunk_size")
        if len(weights) != len(client_ids):
            raise ValueError("robust aggregation requires one weight per client")
        weight_by_client = dict(zip(client_ids, weights))
        ordered_weights = [int(weight_by_client[cid]) for cid, _ in client_count_pairs]
        validate_spec(list(robust_spec), ordered_weights)
        payload.update({
            "program": program,
            "weights": ordered_weights,
            "robust_spec": [int(value) for value in robust_spec],
            "chunk_size": int(chunk_size),
        })
        if direction is not None:
            from fl_security.smpc.robust import validate_direction

            min_agree, indices = validate_direction(direction, int(input_count) - 1)
            payload["direction"] = {"min_agree": min_agree, "indices": indices}
    elif direction is not None:
        raise ValueError("the direction screen requires the robust program")

    hashes = []
    try:
        # Parties compile and launch independently, so the authenticated start
        # requests are sent concurrently; every response is still checked.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(parties)) as pool:
            responses = list(pool.map(
                lambda party: (party, _control_request(party, round_id, "start", payload)),
                parties,
            ))
        for party, response in responses:
            if response.get("status") != "running":
                raise RuntimeError(
                    f"SPDZ2k party {party.party_id} did not start its round"
                )
            program_hash = response.get("program_sha256")
            if not isinstance(program_hash, str) or len(program_hash) != 64:
                raise RuntimeError(
                    f"SPDZ2k party {party.party_id} returned an invalid program hash"
                )
            hashes.append(program_hash)
        if len(set(hashes)) != 1:
            raise RuntimeError("SPDZ2k parties compiled different program bytecode")
    except Exception as exc:
        abort_errors = []
        try:
            abort_round(parties, round_id)
        except Exception as abort_exc:
            abort_errors.append(str(abort_exc))
        details = f"; abort errors: {abort_errors}" if abort_errors else ""
        raise RuntimeError(f"failed to start all SPDZ2k parties: {exc}{details}") from exc


def check_round_running(
    parties: Sequence[MPSpdzParty], round_id: str
) -> None:
    for party in parties:
        response = _control_request(party, round_id, "status", timeout=15.0)
        if response.get("status") != "running":
            raise RuntimeError(
                f"SPDZ2k party {party.party_id} is not running: {response}"
            )


def finish_round(parties: Sequence[MPSpdzParty], round_id: str) -> list[dict]:
    """Wait for every party to exit successfully, clean up, and return statistics.

    The returned list holds, per party, MP-SPDZ's own end-of-run measurements
    (protocol seconds, data sent) when the party log contains them.
    """
    deadline = time.monotonic() + 60.0
    statistics: dict[int, dict] = {}
    while True:
        errors = []
        all_completed = True
        for party in parties:
            try:
                response = _control_request(party, round_id, "status", timeout=15.0)
                if response.get("status") == "completed" and response.get("exit_code") == 0:
                    stats = response.get("statistics")
                    statistics[party.party_id] = dict(stats) if isinstance(stats, dict) else {}
                    continue
                if response.get("status") == "running":
                    all_completed = False
                    continue
                raise RuntimeError(f"party did not complete successfully: {response}")
            except Exception as exc:
                errors.append(f"party {party.party_id}: {exc}")
        if errors:
            raise RuntimeError("SPDZ2k round failed: " + "; ".join(errors))
        if all_completed:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("SPDZ2k parties did not all finish within 60 seconds")
        time.sleep(0.1)

    cleanup_errors = []
    for party in parties:
        try:
            _control_request(party, round_id, "cleanup", timeout=30.0)
        except Exception as exc:
            cleanup_errors.append(f"party {party.party_id}: {exc}")
    if cleanup_errors:
        raise RuntimeError(
            "SPDZ2k round completed, but cleanup failed: "
            + "; ".join(cleanup_errors)
        )
    return [
        {"party_id": party.party_id, **statistics.get(party.party_id, {})}
        for party in parties
    ]


def submit_wire_values(
    wire_values: Sequence[int],
    client_id: int,
    *,
    hosts: Sequence[str],
    port_base: int,
    credentials_dir: str | os.PathLike[str],
    mp_spdz_home: str | os.PathLike[str],
    chunk_size: int,
) -> int:
    """Send an already-encoded, chunk-padded input vector (used for robustness tests).

    Values are reduced modulo the MP-SPDZ input domain by the client library, so
    this function can also express deliberately malformed (wrapping) inputs.
    """
    if not wire_values or len(wire_values) % chunk_size:
        raise ValueError("wire values must be a non-empty multiple of chunk_size")
    client_class = _load_external_io_client_class(mp_spdz_home)
    client = _connect_client(client_class, hosts, port_base, client_id, credentials_dir)
    try:
        for offset in range(0, len(wire_values), chunk_size):
            client.send_private_inputs(list(wire_values[offset : offset + chunk_size]))
    finally:
        _close_client(client)
    return len(wire_values) * 8


def abort_round(parties: Sequence[MPSpdzParty], round_id: str) -> None:
    errors = []
    for party in parties:
        try:
            _control_request(party, round_id, "stop", timeout=15.0)
        except Exception as exc:
            errors.append(f"party {party.party_id}: {exc}")
    for party in parties:
        try:
            _control_request(party, round_id, "cleanup", timeout=30.0)
        except Exception as exc:
            errors.append(f"party {party.party_id}: {exc}")
    if errors:
        raise RuntimeError("SPDZ2k abort cleanup failed: " + "; ".join(errors))
