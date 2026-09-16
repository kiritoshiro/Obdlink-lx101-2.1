import pytest

from notescan.safety.errors import ReplayMismatch, TransportError
from notescan.transport import FakeTransport, ReplayExchange, ReplayTransport


def test_replay_is_ordered_and_offline() -> None:
    transport = ReplayTransport(
        [ReplayExchange(b"\x01\x0c", b"A"), ReplayExchange(b"\x03", b"B")]
    )
    transport.open()
    assert transport.exchange(b"\x01\x0c", 1) == b"A"
    assert transport.exchange(b"\x03", 1) == b"B"
    assert transport.remaining == 0
    transport.close()
    assert not transport.is_open


def test_replay_rejects_unexpected_request() -> None:
    transport = ReplayTransport([ReplayExchange(b"\x01\x0c", b"A")])
    transport.open()
    with pytest.raises(ReplayMismatch):
        transport.exchange(b"\x03", 1)
    assert transport.remaining == 1


def test_fake_transport_supports_a_pure_callable() -> None:
    transport = FakeTransport(lambda request: request + b"\x40")
    transport.open()
    assert transport.exchange(b"\x01\x0c", 1) == b"\x01\x0c\x40"
    transport.close()
    with pytest.raises(TransportError):
        transport.exchange(b"\x03", 1)
