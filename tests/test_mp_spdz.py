import torch
import pytest

from fl_security.smpc.fixed_point import FixedPointEncoder
from fl_security.smpc.mp_spdz import (
    CLIENT_IO_TIMEOUT_SECONDS,
    _encode_weighted_model,
    _connect_client,
    receive_weighted_average,
    _prepare_chunked_client_inputs,
    SPDZ2K_IO_CHUNK_SIZE,
)


def test_weighted_model_encoding_includes_sample_count_and_float_tensors():
    state = {
        "weight": torch.tensor([1.25, -2.0], dtype=torch.float32),
        "counter": torch.tensor([7], dtype=torch.int64),
    }

    encoded, layout = _encode_weighted_model(
        state, num_examples=3, encoder=FixedPointEncoder(100), max_clients=2
    )

    assert encoded == [375, -600, 3]
    assert layout == [("weight", (2,))]


def test_weighted_model_encoding_rejects_ring_overflow():
    with pytest.raises(OverflowError, match="safe SPDZ2k ring range"):
        _encode_weighted_model(
            {"weight": torch.tensor([3e12])},
            num_examples=2,
            encoder=FixedPointEncoder(1_000_000),
            max_clients=2,
        )


def test_client_connections_have_a_bounded_io_timeout(tmp_path):
    class Connection:
        timeout = None

        def settimeout(self, value):
            self.timeout = value

    connection = Connection()

    class Client:
        sockets = [connection]

        def __init__(self, hosts, port_base, client_id):
            self.args = (hosts, port_base, client_id)

    client = _connect_client(Client, ["party0", "party1"], 20_000, 0, tmp_path)

    assert client.args == (["party0", "party1"], 20_000, 0)
    assert connection.timeout == CLIENT_IO_TIMEOUT_SECONDS


def test_output_client_receives_only_weighted_average_and_count(monkeypatch, tmp_path):
    class Client:
        sockets = []

        def receive_outputs(self, count):
            assert count == SPDZ2K_IO_CHUNK_SIZE
            return [3, 300, 600] + [0] * (count - 3)

    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._load_external_io_client_class", lambda mp_home: Client
    )
    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._connect_client",
        lambda *args, **kwargs: Client(),
    )
    global_state = {
        "weight": torch.tensor([0.0, 0.0]),
        "counter": torch.tensor([5], dtype=torch.int64),
    }

    result = receive_weighted_average(
        global_state,
        hosts=["127.0.0.1", "127.0.0.2"],
        port_base=20_000,
        credentials_dir=tmp_path,
        mp_spdz_home=tmp_path,
        output_client_id=3,
        encoder=FixedPointEncoder(100),
        expected_total_examples=3,
    )

    torch.testing.assert_close(result["weight"], torch.tensor([1.0, 2.0]))
    assert result["counter"].item() == 5



def test_output_client_reads_full_array_reveal_in_one_message(monkeypatch, tmp_path):
    calls = []

    class Client:
        sockets = []

        def receive_outputs(self, count):
            calls.append(count)
            assert count == 10_240
            return [6] + [600] * 10_000 + [0] * (count - 10_001)

    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._load_external_io_client_class", lambda mp_home: Client
    )
    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._connect_client",
        lambda *args, **kwargs: Client(),
    )
    result = receive_weighted_average(
        {"weight": torch.zeros(10_000)},
        hosts=["127.0.0.1", "127.0.0.2"],
        port_base=20_000,
        credentials_dir=tmp_path,
        mp_spdz_home=tmp_path,
        output_client_id=3,
        encoder=FixedPointEncoder(100),
        expected_total_examples=6,
    )
    assert calls == [10_240]
    torch.testing.assert_close(result["weight"], torch.ones(10_000))

def test_output_client_rejects_wrong_aggregate_sample_count(monkeypatch, tmp_path):
    class Client:
        sockets = []

        def receive_outputs(self, count):
            return [4, 300, 600] + [0] * (SPDZ2K_IO_CHUNK_SIZE - 3)

    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._load_external_io_client_class", lambda mp_home: Client
    )
    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._connect_client",
        lambda *args, **kwargs: Client(),
    )

    with pytest.raises(RuntimeError, match="sample count"):
        receive_weighted_average(
            {"weight": torch.tensor([0.0, 0.0])},
            hosts=["127.0.0.1", "127.0.0.2"],
            port_base=20_000,
            credentials_dir=tmp_path,
            mp_spdz_home=tmp_path,
            output_client_id=3,
            encoder=FixedPointEncoder(100),
            expected_total_examples=3,
        )


def test_chunked_client_vector_places_count_first_and_zero_pads():
    wire = _prepare_chunked_client_inputs([375, -600, 3], chunk_size=4)
    assert wire == [3, 375, -600, 0]
    assert len(wire) % 4 == 0


def test_chunked_client_vector_rejects_invalid_count():
    with pytest.raises(ValueError, match="positive integer"):
        _prepare_chunked_client_inputs([10, 0], chunk_size=4)



def test_output_client_rejects_truncated_full_array(monkeypatch, tmp_path):
    class Client:
        sockets = []

        def receive_outputs(self, count):
            assert count == SPDZ2K_IO_CHUNK_SIZE
            return [3, 300, 600]

    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._load_external_io_client_class", lambda mp_home: Client
    )
    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._connect_client",
        lambda *args, **kwargs: Client(),
    )
    with pytest.raises(RuntimeError, match="output length"):
        receive_weighted_average(
            {"weight": torch.zeros(2)},
            hosts=["127.0.0.1", "127.0.0.2"],
            port_base=20_000,
            credentials_dir=tmp_path,
            mp_spdz_home=tmp_path,
            output_client_id=3,
            encoder=FixedPointEncoder(100),
            expected_total_examples=3,
        )


def test_output_client_rejects_nonzero_padding_tail(monkeypatch, tmp_path):
    class Client:
        sockets = []

        def receive_outputs(self, count):
            values = [3, 300, 600] + [0] * (count - 3)
            values[-1] = 1
            return values

    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._load_external_io_client_class", lambda mp_home: Client
    )
    monkeypatch.setattr(
        "fl_security.smpc.mp_spdz._connect_client",
        lambda *args, **kwargs: Client(),
    )
    with pytest.raises(RuntimeError, match="padded output tail"):
        receive_weighted_average(
            {"weight": torch.zeros(2)},
            hosts=["127.0.0.1", "127.0.0.2"],
            port_base=20_000,
            credentials_dir=tmp_path,
            mp_spdz_home=tmp_path,
            output_client_id=3,
            encoder=FixedPointEncoder(100),
            expected_total_examples=3,
        )
