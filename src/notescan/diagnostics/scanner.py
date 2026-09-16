"""Safe orchestration from bounded transport results to evidence sessions.

The scanner deliberately has no free-form command path. A caller either uses
the finite default plan or supplies typed ``DiagnosticRequest`` values, which
are validated in full by :class:`~notescan.safety.scheduler.SafeScheduler`
before the transport is opened.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from notescan.domain.models import DiagnosticSession, VehicleProfile, utc_now
from notescan.safety.operations import DiagnosticRequest, Operation
from notescan.safety.policy import LIVE_DATA_PIDS
from notescan.safety.scheduler import SafeScheduler, ScanReport, ScanResult, SessionState
from notescan.storage.json_store import SessionStore

from .decoders import (
    DecoderError,
    decode_dtc_response,
    decode_pid_response,
    decode_readiness_response,
    decode_vin_response,
)


def default_scan_requests() -> tuple[DiagnosticRequest, ...]:
    """Return the finite generic engine/emissions read plan.

    The plan performs standard identification, readiness, DTC and live-data
    reads only. It does not include code clearing, actuator controls, ECU
    writes, Nissan enhanced services, or freeze-frame reads by default.
    """

    requests: list[DiagnosticRequest] = [
        DiagnosticRequest(Operation.SUPPORTED_PIDS, 0x00),
        DiagnosticRequest(Operation.READINESS),
        DiagnosticRequest(Operation.VEHICLE_IDENTIFICATION),
        DiagnosticRequest(Operation.STORED_CODES),
        DiagnosticRequest(Operation.PENDING_CODES),
        DiagnosticRequest(Operation.PERMANENT_CODES),
    ]
    requests.extend(
        DiagnosticRequest(Operation.LIVE_DATA, pid) for pid in sorted(LIVE_DATA_PIDS)
    )
    return tuple(requests)


@dataclass(frozen=True, slots=True)
class ScanCapture:
    """Decoded session plus the scheduler evidence that produced it."""

    session: DiagnosticSession
    report: ScanReport
    saved_path: Path | None = None


class SafeScanner:
    """Run one explicit, finite read-only plan and preserve every response."""

    def __init__(
        self,
        scheduler: SafeScheduler,
        *,
        store: SessionStore | None = None,
        vehicle: VehicleProfile | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.scheduler = scheduler
        self.store = store
        self.vehicle = vehicle or VehicleProfile()
        self._now = now

    def run(
        self,
        requests: Iterable[DiagnosticRequest] | None = None,
        *,
        session_id: str | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> ScanCapture:
        """Execute a plan, decode supported responses, and optionally save it."""

        started_at = self._now()
        identifier = session_id or self._new_session_id(started_at)
        plan = tuple(requests) if requests is not None else default_scan_requests()
        report = self.scheduler.run(plan, stop_check=stop_check)
        session = DiagnosticSession(
            session_id=identifier,
            vehicle=VehicleProfile.from_dict(self.vehicle.to_dict()),
            started_at=started_at,
            ended_at=self._now(),
            complete=report.state is SessionState.COMPLETE,
        )
        for result in report.results:
            self._record_result(session, result)
        if report.error:
            session.notes.append(f"Scan ended with {report.state.value}: {report.error}")
        if report.state is not SessionState.COMPLETE:
            session.notes.append("Partial evidence was preserved; start a new scan to retry.")

        saved_path: Path | None = None
        if self.store is not None:
            saved_path = self.store.save(session)
        return ScanCapture(session=session, report=report, saved_path=saved_path)

    @staticmethod
    def _new_session_id(started_at: datetime) -> str:
        stamp = started_at.astimezone().strftime("%Y%m%d-%H%M%S")
        return f"safescan-{stamp}-{uuid4().hex[:8]}"

    def _record_result(self, session: DiagnosticSession, result: ScanResult) -> None:
        response_text = result.response.decode("ascii", errors="replace").strip()
        if not response_text or any(ord(char) < 0x20 for char in response_text):
            response_text = result.response.hex(" ").upper()
        session.raw_frames.append(
            {
                "timestamp": self._now().isoformat(),
                "request": result.request.hex(" ").upper(),
                "response": response_text,
                "response_bytes": result.response.hex(" ").upper(),
                "operation": result.operation.value,
                "elapsed_s": round(result.elapsed_s, 6),
                "ecu": "engine",
            }
        )
        try:
            if result.operation is Operation.LIVE_DATA:
                session.measurements.append(
                    decode_pid_response(
                        result.response,
                        ecu="engine",
                        source="obd2-live",
                    )
                )
            elif result.operation is Operation.FREEZE_FRAME:
                session.measurements.append(
                    decode_pid_response(
                        result.response,
                        ecu="engine",
                        source="obd2-freeze-frame",
                        positive_service=0x42,
                    )
                )
            elif result.operation is Operation.READINESS:
                session.readiness = decode_readiness_response(result.response)
            elif result.operation is Operation.STORED_CODES:
                session.trouble_codes.extend(
                    decode_dtc_response(result.response, status="stored", positive_service=0x43)
                )
            elif result.operation is Operation.PENDING_CODES:
                session.trouble_codes.extend(
                    decode_dtc_response(result.response, status="pending", positive_service=0x47)
                )
            elif result.operation is Operation.PERMANENT_CODES:
                session.trouble_codes.extend(
                    decode_dtc_response(
                        result.response,
                        status="permanent",
                        positive_service=0x4A,
                    )
                )
            elif result.operation is Operation.VEHICLE_IDENTIFICATION:
                session.vehicle.vin = decode_vin_response(result.response)
            elif result.operation is Operation.SUPPORTED_PIDS:
                session.notes.append("Supported PID bitmap preserved in raw_frames.")
        except (DecoderError, ValueError) as exc:
            session.notes.append(
                f"Could not decode {result.operation.value} response: {exc}"
            )
