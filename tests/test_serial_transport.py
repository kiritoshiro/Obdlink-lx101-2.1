import pytest

from notescan.safety.errors import PolicyViolation, TransportError
from notescan.transport import SerialConfig, SerialTransport


class FakeSerial:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.timeout = kwargs.get("timeout")
        self.is_open = True
        self.writes: list[bytes] = []
        self.responses = [b"OK\r>"] * 6 + [b"OBDLink LX\r>"] + [b"STN1155\r>"]
        self.responses.extend([b"STN firmware\r>", b"OBD Solutions\r>"])
        self.closed = False

    def reset_input_buffer(self):
        return None

    def reset_output_buffer(self):
        return None

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def read_until(self, expected: bytes = b"\n", size=None) -> bytes:
        return self.responses.pop(0) if self.responses else b"41 0C 1A F8\r>"

    def close(self):
        self.closed = True
        self.is_open = False

    def open(self):
        self.is_open = True


def test_serial_config_accepts_windows_com_names_only() -> None:
    assert SerialConfig("COM7").port == "COM7"
    assert SerialConfig(r"\\.\COM10").port == r"\\.\COM10"
    with pytest.raises(ValueError):
        SerialConfig("/dev/ttyUSB0")


def test_serial_transport_initialises_adapter_and_exchanges_read() -> None:
    fake = FakeSerial()
    transport = SerialTransport(
        SerialConfig("COM7"),
        serial_factory=lambda **kwargs: fake,
    )
    transport.open()
    assert transport.adapter_identity == b"OBDLink LX"
    assert transport.identity_responses["STDI"] == b"STN1155"
    assert transport.exchange(b"\x01\x0c", 1) == b"41 0C 1A F8"
    assert fake.writes[-1] == b"010C\r"
    transport.close()
    assert not transport.is_open


def test_serial_transport_rejects_non_read_payload_before_io() -> None:
    fake = FakeSerial()
    transport = SerialTransport(SerialConfig("COM7"), serial_factory=lambda **kwargs: fake)
    transport.open()
    with pytest.raises(PolicyViolation):
        transport.exchange(b"\x04", 1)
    assert fake.writes[-1] == b"STMFR\r"
    assert len(fake.writes) == 10
    transport.close()


def test_serial_transport_fails_on_empty_reply_and_closes() -> None:
    fake = FakeSerial()
    fake.responses = [b"OK\r>"] * 6 + [b"OBDLink LX\r>"]
    fake.responses.extend([b"STN1155\r>", b"STN firmware\r>", b"OBD Solutions\r>", b""])
    transport = SerialTransport(SerialConfig("COM7"), serial_factory=lambda **kwargs: fake)
    transport.open()
    with pytest.raises(TransportError):
        transport.exchange(b"\x01\x0c", 1)
    transport.close()
