"""Regressions for how the scanner drives and interprets a real adapter.

These cover the differences between a tidy fixture and an ELM327-compatible
adapter on a CAN vehicle: protocol-search chatter before the first reply,
``NO DATA`` instead of an ECU response, and the DTC count byte.
"""

from notescan.diagnostics.analyzer import analyze_session
from notescan.diagnostics.scanner import SafeScanner
from notescan.safety import SafeScheduler, SchedulerConfig
from notescan.transport import FakeTransport


class CountingTransport(FakeTransport):
    """Fake transport that records how often the port was opened."""

    def __init__(self, responses: dict[bytes, bytes]) -> None:
        super().__init__(responses)
        self.opens = 0

    def open(self) -> None:
        self.opens += 1
        super().open()


def _responses(**overrides: bytes) -> dict[bytes, bytes]:
    base = {
        b"\x01\x00": b"41 00 80 00 00 01",  # advertise PID 01 and 20 only
        b"\x01\x01": b"41 01 00 07 01 00",
        b"\x09\x02": b"\x49\x02\x01WVWZZZ1JZXW000001",
        b"\x03": b"43 00 00",
        b"\x07": b"47 00 00",
        b"\x0a": b"4A 00 00",
    }
    for key, value in overrides.items():
        base[bytes.fromhex(key)] = value
    return base


def _scanner(transport: FakeTransport) -> SafeScanner:
    return SafeScanner(SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0)))


def test_default_scan_opens_the_transport_once() -> None:
    """Reopening mid-scan would reset the adapter and re-run protocol search."""

    transport = CountingTransport(_responses())

    capture = _scanner(transport).run(session_id="single-open-1")

    assert capture.session.complete
    assert transport.opens == 1


def test_protocol_search_chatter_does_not_defeat_pid_discovery() -> None:
    transport = FakeTransport(_responses(**{"0100": b"SEARCHING...\r41 00 80 00 00 01"}))

    capture = _scanner(transport).run(session_id="searching-1")

    assert capture.session.metadata["supported_pids"] == ["01", "20"]
    assert not any("Could not decode supported_pids" in note for note in capture.session.notes)


def test_can_dtc_count_byte_is_decoded_not_treated_as_a_code() -> None:
    transport = FakeTransport(_responses(**{"03": b"43 02 01 33 01 96 00 00"}))

    capture = _scanner(transport).run(session_id="can-dtc-1")

    assert [item.code for item in capture.session.trouble_codes] == ["P0133", "P0196"]


def test_no_data_is_recorded_as_an_adapter_status_not_a_decoder_failure() -> None:
    transport = FakeTransport(_responses(**{"0902": b"NO DATA"}))

    capture = _scanner(transport).run(session_id="no-data-1")

    assert capture.session.vehicle.vin is None
    assert any("Adapter reported NO DATA" in note for note in capture.session.notes)
    assert not any("Could not decode" in note for note in capture.session.notes)
    assert "vehicle_identification" not in capture.session.metadata["decoded_operations"]


def test_analysis_does_not_claim_absent_codes_when_the_stored_read_failed() -> None:
    transport = FakeTransport(_responses(**{"03": b"NO DATA"}))

    capture = _scanner(transport).run(session_id="unconfirmed-1")
    titles = [finding.title for finding in analyze_session(capture.session)]

    assert "Stored codes were not confirmed" in titles
    assert "No stored generic engine codes" not in titles


def test_analysis_still_reports_a_confirmed_clean_stored_read() -> None:
    transport = FakeTransport(_responses())

    capture = _scanner(transport).run(session_id="clean-1")
    titles = [finding.title for finding in analyze_session(capture.session)]

    assert "No stored generic engine codes" in titles
    assert "stored_codes" in capture.session.metadata["decoded_operations"]
