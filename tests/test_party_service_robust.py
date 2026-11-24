"""Party-service validation for the robust SPDZ2k program (no MPC processes)."""
import pytest

from fl_security.smpc.mp_spdz_party_service import MPSpdzPartyService, ROBUST_PROGRAM
from fl_security.smpc.robust import SecureDefenceConfig


def _service():
    service = object.__new__(MPSpdzPartyService)
    service.client_port_base = 20_000
    return service


def _payload(**overrides):
    config = SecureDefenceConfig(mode="clip_screen", threshold="adaptive")
    payload = {
        "client_ids": [4, 1],
        "input_count": 11,
        "expected_counts": [400, 100],
        "output_client_id": 9,
        "client_port_base": 20_000,
        "program": ROBUST_PROGRAM,
        "weights": [1, 1],
        "robust_spec": config.round_spec([1, 1]),
        "chunk_size": 16,
    }
    payload.update(overrides)
    return payload


def test_robust_identity_uses_short_name_and_sorted_arguments():
    identity = _service()._program_identity("round-7", _payload())
    assert identity.kind == ROBUST_PROGRAM
    assert identity.program_name == identity.program_base
    assert identity.args[:3] == ["1,4", "100,400", "1,1"]
    assert identity.args[3:7] == ["11", "9", "20000", "16"]
    base, name, _ = identity              # still supports three-value unpacking
    assert base == name


@pytest.mark.parametrize("change", [
    {"weights": [1]},
    {"weights": [0, 1]},
    {"weights": [True, 1]},
    {"chunk_size": 8},
    {"robust_spec": [1, 2, 3]},
    {"robust_spec": [1, 1, 1, 10, 1, 10, 1, 4, 8, 1 << 62, 1, 0, 0]},
    {"unexpected": 1},
    {"program": "something_else"},
])
def test_robust_identity_rejects_invalid_payloads(change):
    with pytest.raises(ValueError):
        _service()._program_identity("round-7", _payload(**change))


def test_weighted_sum_identity_rejects_robust_only_fields():
    payload = {
        "client_ids": [0, 1], "input_count": 10, "expected_counts": [1, 2],
        "output_client_id": 2, "client_port_base": 20_000, "weights": [1, 1],
    }
    with pytest.raises(ValueError, match="unexpected"):
        _service()._program_identity("round-1", payload)


def test_protocol_statistics_are_parsed_from_party_log():
    text = (
        "Time = 8.00099 seconds \n"
        "Data sent = 424.6 MB in ~2204 rounds (party 0 only; use '-v' for more details)\n"
        "Global data sent = 1273.25 MB (all parties)\n"
    )
    stats = MPSpdzPartyService._protocol_statistics(text)
    assert stats == {
        "protocol_seconds": 8.00099, "party_data_sent_mb": 424.6,
        "party_rounds": 2204.0, "global_data_sent_mb": 1273.25,
    }
    assert MPSpdzPartyService._protocol_statistics("no summary") == {}


def test_cleanup_removes_all_tapes_of_the_round(tmp_path):
    for sub in ("Source", "Schedules", "Bytecode"):
        (tmp_path / "Programs" / sub).mkdir(parents=True)
    name = "fl_spdz_abc"
    files = [
        tmp_path / "Programs" / "Source" / f"{name}.mpc",
        tmp_path / "Programs" / "Schedules" / f"{name}.sch",
        tmp_path / "Programs" / "Bytecode" / f"{name}-0.bc",
        tmp_path / "Programs" / "Bytecode" / f"{name}-LTZ(8)_64-3.bc",
    ]
    other = tmp_path / "Programs" / "Bytecode" / "fl_spdz_other-0.bc"
    for path in files + [other]:
        path.write_text("x")
    service = object.__new__(MPSpdzPartyService)
    import threading

    service.lock = threading.RLock()
    service.current = None
    service.mp_home = tmp_path
    service.round_metadata = {"round-1": (name, name)}
    assert service.cleanup("round-1") == {"status": "cleaned"}
    assert not any(path.exists() for path in files)
    assert other.exists()
