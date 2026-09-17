"""Finite, stoppable sequencing of validated read operations."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from time import monotonic, sleep

from notescan.transport.base import DiagnosticTransport

from .errors import SafetyError, SessionLimitExceeded
from .operations import DiagnosticRequest, Operation, ValidatedRequest, encode_request
from .policy import SafetyPolicy


class SessionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETE = "complete"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SchedulerConfig:
    max_requests: int = 64
    request_timeout_s: float = 2.0
    min_interval_s: float = 0.05

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_requests, bool)
            or not isinstance(self.max_requests, int)
            or self.max_requests < 1
        ):
            raise ValueError("max_requests must be a positive integer")
        if self.request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be positive")
        if self.min_interval_s < 0:
            raise ValueError("min_interval_s cannot be negative")


@dataclass(frozen=True, slots=True)
class ScanResult:
    operation: Operation
    request: bytes
    response: bytes
    elapsed_s: float


@dataclass(frozen=True, slots=True)
class ScanReport:
    state: SessionState
    results: tuple[ScanResult, ...]
    error: str | None = None


@dataclass
class _Session:
    state: SessionState = SessionState.DISCONNECTED
    requests_sent: int = 0
    stop_requested: bool = False
    failure: str | None = None


class SafeScheduler:
    """Execute a finite batch after validating the entire batch.

    The scheduler has no reconnect or resume behavior.  A transport failure
    ends the session and closes the transport; a later scan must be started by
    the caller as a new session.
    """

    def __init__(
        self,
        transport: DiagnosticTransport,
        *,
        policy: SafetyPolicy | None = None,
        config: SchedulerConfig | None = None,
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.transport = transport
        self.policy = policy or SafetyPolicy()
        self.config = config or SchedulerConfig()
        self._sleep = sleeper
        self._clock = clock
        self._session: _Session | None = None

    @property
    def state(self) -> SessionState:
        return self._session.state if self._session else SessionState.DISCONNECTED

    def stop(self) -> None:
        """Request a clean stop at the next scheduler boundary."""

        if self._session and self._session.state in (
            SessionState.CONNECTING,
            SessionState.READY,
            SessionState.RUNNING,
        ):
            self._session.stop_requested = True
            self._session.state = SessionState.STOPPING

    def run(
        self,
        requests: Iterable[DiagnosticRequest],
        *,
        stop_check: Callable[[], bool] | None = None,
        request_filter: Callable[[ValidatedRequest, tuple[ScanResult, ...]], bool] | None = None,
    ) -> ScanReport:
        """Run requests and return evidence, including partial scans.

        All policy checks happen before ``transport.open``.  ``stop_check`` is
        injected for a GUI cancel button and remains an observation only; it
        cannot alter or submit a command.

        ``request_filter`` may drop an already-validated request in light of the
        responses received so far, which lets one session adapt to what the ECU
        advertises without reopening the transport.  It can only remove work:
        it never sees an unvalidated request and cannot add, alter or reorder
        one, so the pre-open validation guarantee is unchanged.
        """

        if self._session and self._session.state in {
            SessionState.CONNECTING,
            SessionState.READY,
            SessionState.RUNNING,
            SessionState.STOPPING,
        }:
            raise SafetyError("a scan session is already active")
        validated = self.policy.validate_batch(requests)
        if len(validated) > self.config.max_requests:
            raise SessionLimitExceeded(
                f"scan contains {len(validated)} requests; limit is {self.config.max_requests}"
            )
        session = _Session()
        self._session = session
        results: list[ScanResult] = []
        opened = False
        try:
            session.state = SessionState.CONNECTING
            try:
                self.transport.open()
                opened = True
            except Exception as exc:
                session.failure = str(exc)
                session.state = SessionState.FAILED
                return ScanReport(session.state, tuple(results), session.failure)
            session.state = SessionState.READY
            for request in validated:
                if session.stop_requested or (stop_check is not None and stop_check()):
                    session.state = SessionState.STOPPED
                    break
                if request_filter is not None and not request_filter(request, tuple(results)):
                    continue
                if session.requests_sent:
                    self._sleep(self.config.min_interval_s)
                    if session.stop_requested or (stop_check is not None and stop_check()):
                        session.state = SessionState.STOPPED
                        break
                session.state = SessionState.RUNNING
                wire_request = encode_request(request)
                started = self._clock()
                try:
                    response = self.transport.exchange(wire_request, self.config.request_timeout_s)
                except Exception as exc:
                    session.failure = str(exc)
                    session.state = SessionState.FAILED
                    break
                if not isinstance(response, bytes):
                    session.failure = "transport returned a non-bytes response"
                    session.state = SessionState.FAILED
                    break
                session.requests_sent += 1
                results.append(
                    ScanResult(request.operation, wire_request, response, self._clock() - started)
                )
            else:
                session.state = SessionState.COMPLETE
        finally:
            if opened:
                try:
                    self.transport.close()
                except Exception as exc:
                    if session.failure is None:
                        session.failure = str(exc)
                        session.state = SessionState.FAILED
            if session.state is SessionState.READY:
                session.state = SessionState.COMPLETE
        return ScanReport(session.state, tuple(results), session.failure)
