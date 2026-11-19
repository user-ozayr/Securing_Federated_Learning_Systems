import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from fl_security.smpc import mp_spdz
from fl_security.smpc.mp_spdz_party_service import (
    MPSpdzPartyService,
    create_handler,
)


class _ControlService:
    def __init__(self):
        self.control_token = "party-control-token-" + ("x" * 32)
        self.party_id = 0
        self.requests = set()

    def consume_control_request(self, request_id, timestamp):
        del timestamp
        if request_id in self.requests:
            return False
        self.requests.add(request_id)
        return True

    def status(self, round_id):
        return {"status": "running", "round_id": round_id}


def _signed_request(url, secret, route, request_id, timestamp=None, signature=True):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    body = b"{}"
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
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not signature:
        digest = "0" * 64
    return urllib.request.Request(
        url + route,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Request-ID": request_id,
            "X-Signature": digest,
        },
        method="POST",
    )


def test_party_control_authenticates_and_rejects_replayed_requests():
    service = _ControlService()
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        route = "/v1/rounds/test-round/status"
        party = mp_spdz.MPSpdzParty(
            0, url, service.control_token, "127.0.0.1"
        )
        assert mp_spdz._control_request(
            party, "test-round", "status"
        )["status"] == "running"
        request = _signed_request(
            url, service.control_token, route, "a" * 64
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert json.loads(response.read())["status"] == "running"

        with pytest.raises(urllib.error.HTTPError) as replay:
            urllib.request.urlopen(request, timeout=2)
        assert replay.value.code == 409

        invalid_signature = _signed_request(
            url, service.control_token, route, "b" * 64, signature=False
        )
        with pytest.raises(urllib.error.HTTPError) as invalid:
            urllib.request.urlopen(invalid_signature, timeout=2)
        assert invalid.value.code == 401

        stale = _signed_request(
            url,
            service.control_token,
            route,
            "c" * 64,
            timestamp=int(time.time()) - 301,
        )
        with pytest.raises(urllib.error.HTTPError) as expired:
            urllib.request.urlopen(stale, timeout=2)
        assert expired.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_control_request_replay_journal_survives_service_restart(tmp_path: Path):
    journal = tmp_path / "used-control-requests.jsonl"
    first = object.__new__(MPSpdzPartyService)
    first.lock = threading.RLock()
    first.seen_control_requests_path = journal
    first.seen_control_requests = {}
    request_id, timestamp = "d" * 64, int(time.time())

    assert first.consume_control_request(request_id, timestamp)

    restarted = object.__new__(MPSpdzPartyService)
    restarted.lock = threading.RLock()
    restarted.seen_control_requests_path = journal
    restarted.seen_control_requests = (
        MPSpdzPartyService._load_seen_control_requests(restarted)
    )
    assert not restarted.consume_control_request(request_id, timestamp)


def test_round_start_failure_triggers_abort_and_cleanup(monkeypatch):
    parties = [
        SimpleNamespace(party_id=0),
        SimpleNamespace(party_id=1),
    ]
    aborts = []

    def request(party, round_id, action, payload=None, timeout=600.0):
        del round_id, payload, timeout
        if party.party_id == 1:
            raise RuntimeError("party compile failed")
        if action == "start":
            return {"status": "running", "program_sha256": "a" * 64}
        return {"status": "cleaned"}

    monkeypatch.setattr(mp_spdz, "_control_request", request)
    monkeypatch.setattr(
        mp_spdz, "abort_round", lambda requested, round_id: aborts.append(
            (requested, round_id)
        )
    )

    with pytest.raises(RuntimeError, match="failed to start all SPDZ2k parties"):
        mp_spdz.start_round(
            parties,
            "round-1",
            [0, 1],
            input_count=10,
            expected_counts=[100, 200],
            output_client_id=2,
            port_base=20_000,
        )
    assert aborts == [(parties, "round-1")]


def test_program_identity_requires_server_known_sample_counts(tmp_path):
    service = object.__new__(MPSpdzPartyService)
    service.client_port_base = 20000
    with pytest.raises(ValueError, match="expected_counts"):
        service._program_identity("round-1", {
            "client_ids": [0, 1],
            "input_count": 10,
            "expected_counts": [100],
            "output_client_id": 2,
            "client_port_base": 20000,
        })



def test_program_identity_binds_round_cohort_and_expected_counts():
    service = object.__new__(MPSpdzPartyService)
    service.client_port_base = 20_000
    payload = {
        "client_ids": [2, 0],
        "input_count": 1024,
        "expected_counts": [300, 100],
        "output_client_id": 3,
        "client_port_base": 20_000,
    }

    base_a, name_a, args_a = service._program_identity("round-1", payload)
    base_other_round, name_other_round, _ = service._program_identity(
        "round-2", payload
    )
    changed_cohort = dict(payload, client_ids=[1, 2], expected_counts=[200, 300])
    base_same_round, name_other_cohort, _ = service._program_identity(
        "round-1", changed_cohort
    )

    assert base_a != base_other_round
    assert name_a != name_other_round
    assert base_same_round == base_a
    assert name_a != name_other_cohort
    assert args_a[:2] == ["0,2", "100,300"]



def test_party_service_rejects_reused_round_id():
    service = object.__new__(MPSpdzPartyService)
    service.lock = threading.RLock()
    service.current = None
    service.seen_round_ids = {"round-1"}

    with pytest.raises(RuntimeError, match="round ID has already been used"):
        service.start("round-1", {})
