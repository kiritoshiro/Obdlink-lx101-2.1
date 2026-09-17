from datetime import UTC, datetime
from types import SimpleNamespace

from notescan.diagnostics.scanner import SafeScanner, default_scan_requests
from notescan.safety import DiagnosticRequest, Operation, SafeScheduler, SchedulerConfig
from notescan.storage import SessionStore
from notescan.transport import FakeTransport


class MetadataTransport(FakeTransport):
    config = SimpleNamespace(port="COM7")
    adapter_identity = b"OBDLink LX"
    identity_responses = {"ATI": b"OBDLink LX", "STI": b"STN firmware"}


def test_default_plan_is_finite_and_read_only() -> None:
    plan = default_scan_requests()
    assert len(plan) == 19
    assert all(isinstance(item, DiagnosticRequest) for item in plan)
    assert all(item.operation is not Operation.FREEZE_FRAME for item in plan)


def test_scanner_decodes_and_persists_generic_evidence(tmp_path) -> None:
    responses = {
        b"\x01\x01": b"41 01 00 07 07",
        b"\x09\x02": b"\x49\x02\x01WVWZZZ1JZXW000001",
        b"\x03": b"43 01 33 00 00",
        b"\x07": b"47 00 00",
        b"\x0A": b"4A 00 00",
        b"\x01\x0C": b"41 0C 01 F4",
    }
    transport = FakeTransport(responses)
    scanner = SafeScanner(
        SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0)),
        store=SessionStore(tmp_path),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    capture = scanner.run(
        [
            DiagnosticRequest(Operation.READINESS),
            DiagnosticRequest(Operation.VEHICLE_IDENTIFICATION),
            DiagnosticRequest(Operation.STORED_CODES),
            DiagnosticRequest(Operation.PENDING_CODES),
            DiagnosticRequest(Operation.PERMANENT_CODES),
            DiagnosticRequest(Operation.LIVE_DATA, 0x0C),
        ],
        session_id="scan-1",
    )

    assert capture.session.complete
    assert capture.report.error is None
    assert capture.saved_path == tmp_path / "scan-1.json"
    assert capture.session.vehicle.vin == "WVWZZZ1JZXW000001"
    assert capture.session.readiness is not None
    assert capture.session.measurements[0].value == 125.0
    assert [(item.code, item.status) for item in capture.session.trouble_codes] == [
        ("P0133", "stored")
    ]
    assert capture.session.raw_frames[0]["response"] == "41 01 00 07 07"
    assert capture.session.raw_frames[0]["response_bytes"] == (
        "34 31 20 30 31 20 30 30 20 30 37 20 30 37"
    )
    assert len(capture.session.raw_frames) == 6


def test_scanner_preserves_partial_failure_and_saves_it(tmp_path) -> None:
    transport = FakeTransport({b"\x01\x0C": b"41 0C 01 F4"})
    scanner = SafeScanner(
        SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0)),
        store=SessionStore(tmp_path),
    )
    capture = scanner.run(
        [
            DiagnosticRequest(Operation.LIVE_DATA, 0x0C),
            DiagnosticRequest(Operation.LIVE_DATA, 0x05),
        ],
        session_id="partial-1",
    )

    assert not capture.session.complete
    assert capture.report.state.value == "failed"
    assert len(capture.session.measurements) == 1
    assert any("Partial evidence" in note for note in capture.session.notes)
    assert capture.saved_path == tmp_path / "partial-1.json"


def test_scanner_records_transport_metadata(tmp_path) -> None:
    transport = MetadataTransport({b"\x01\x0C": b"41 0C 01 F4"})
    scanner = SafeScanner(
        SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0)),
        store=SessionStore(tmp_path),
    )
    capture = scanner.run(
        [DiagnosticRequest(Operation.LIVE_DATA, 0x0C)],
        session_id="metadata-1",
    )

    assert capture.session.metadata["transport"] == "MetadataTransport"
    assert capture.session.metadata["scan_plan_requests"] == 1
    assert capture.session.metadata["port"] == "COM7"
    assert capture.session.metadata["adapter_identity"] == "OBDLink LX"
    assert capture.session.metadata["adapter_setup_responses"]["STI"] == "STN firmware"
    assert SessionStore(tmp_path).load("metadata-1").metadata == capture.session.metadata


def test_scanner_records_supported_pids_and_negative_responses() -> None:
    transport = FakeTransport(
        {
            b"\x01\x00": b"41 00 80 00 00 01",
            b"\x01\x0C": b"7F 01 12",
        }
    )
    scanner = SafeScanner(
        SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0)),
    )
    capture = scanner.run(
        [
            DiagnosticRequest(Operation.SUPPORTED_PIDS, 0x00),
            DiagnosticRequest(Operation.LIVE_DATA, 0x0C),
        ],
        session_id="support-1",
    )

    assert capture.session.complete
    assert capture.session.metadata["supported_pids"] == ["01", "20"]
    assert any("not advertised" in note for note in capture.session.notes)
    assert any("negative response" in note for note in capture.session.notes)
    assert capture.session.measurements == []
