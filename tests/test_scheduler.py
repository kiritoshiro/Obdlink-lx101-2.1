from notescan.safety import (
    DiagnosticRequest,
    Operation,
    SafeScheduler,
    SchedulerConfig,
    SessionState,
)
from notescan.safety.errors import PolicyViolation
from notescan.transport import FakeTransport, ReplayExchange, ReplayTransport


def test_scheduler_runs_finite_batch_and_closes_transport() -> None:
    transport = ReplayTransport(
        [ReplayExchange(b"\x01\x0c", b"rpm"), ReplayExchange(b"\x01\x05", b"coolant")]
    )
    scheduler = SafeScheduler(
        transport,
        config=SchedulerConfig(min_interval_s=0),
    )
    report = scheduler.run(
        [
            DiagnosticRequest(Operation.LIVE_DATA, 0x0C),
            DiagnosticRequest(Operation.LIVE_DATA, 0x05),
        ]
    )
    assert report.state is SessionState.COMPLETE
    assert [result.request for result in report.results] == [b"\x01\x0c", b"\x01\x05"]
    assert [result.response for result in report.results] == [b"rpm", b"coolant"]
    assert not transport.is_open


def test_scheduler_validates_all_requests_before_open() -> None:
    transport = FakeTransport({b"\x01\x0c": b"ok"})
    scheduler = SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0))
    try:
        scheduler.run(
            [
                DiagnosticRequest(Operation.LIVE_DATA, 0x0C),
                DiagnosticRequest(Operation.LIVE_DATA, 0x04),
            ]
        )
    except PolicyViolation:
        pass
    else:
        raise AssertionError("invalid request unexpectedly ran")
    assert not transport.is_open
    assert transport.requests == []


def test_scheduler_can_be_stopped_without_resuming() -> None:
    transport = FakeTransport({b"\x01\x0c": b"ok", b"\x05": b"ok"})
    checks = 0

    def stop_after_first() -> bool:
        nonlocal checks
        checks += 1
        return checks > 2

    scheduler = SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0))
    report = scheduler.run(
        [
            DiagnosticRequest(Operation.LIVE_DATA, 0x0C),
            DiagnosticRequest(Operation.LIVE_DATA, 0x05),
        ],
        stop_check=stop_after_first,
    )
    assert report.state is SessionState.STOPPED
    assert len(report.results) == 1
    assert transport.requests == [b"\x01\x0c"]


def test_scheduler_returns_partial_failed_report_and_closes() -> None:
    transport = ReplayTransport([ReplayExchange(b"\x01\x0c", b"ok")])
    scheduler = SafeScheduler(transport, config=SchedulerConfig(min_interval_s=0))
    report = scheduler.run(
        [DiagnosticRequest(Operation.LIVE_DATA, 0x0C), DiagnosticRequest(Operation.LIVE_DATA, 0x05)]
    )
    assert report.state is SessionState.FAILED
    assert len(report.results) == 1
    assert report.error
    assert not transport.is_open
