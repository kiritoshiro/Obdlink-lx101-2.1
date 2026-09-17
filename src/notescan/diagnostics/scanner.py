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
from typing import Any
from uuid import uuid4

from notescan.domain.models import DiagnosticSession, VehicleProfile, utc_now
from notescan.safety.operations import DiagnosticRequest, Operation, ValidatedRequest
from notescan.safety.policy import LIVE_DATA_PIDS
from notescan.safety.scheduler import SafeScheduler, ScanReport, ScanResult, SessionState
from notescan.storage.json_store import SessionStore

from .decoders import (
    AdapterStatusResponse,
    DecoderError,
    decode_dtc_response,
    decode_negative_response,
    decode_pid_response,
    decode_readiness_response,
    decode_supported_pids_response,
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
        is_default_plan = requests is None
        plan = tuple(requests) if requests is not None else default_scan_requests()
        report, live_skip_reason = self._run_plan(
            plan,
            adaptive=is_default_plan,
            stop_check=stop_check,
        )
        session = DiagnosticSession(
            session_id=identifier,
            vehicle=VehicleProfile.from_dict(self.vehicle.to_dict()),
            started_at=started_at,
            ended_at=self._now(),
            complete=report.state is SessionState.COMPLETE,
        )
        session.metadata.update(self._transport_metadata(len(plan)))
        session.metadata["executed_plan_requests"] = len(report.results)
        session.metadata["decoded_operations"] = []
        session.metadata["requested_live_pids"] = [
            f"{request.pid:02X}"
            for request in plan
            if request.operation is Operation.LIVE_DATA and request.pid is not None
        ]
        if live_skip_reason:
            session.notes.append(live_skip_reason)
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

    def _run_plan(
        self,
        plan: tuple[DiagnosticRequest, ...],
        *,
        adaptive: bool,
        stop_check: Callable[[], bool] | None,
    ) -> tuple[ScanReport, str | None]:
        """Run a plan, discovering supported live PIDs before default reads.

        Explicit plans stay exactly as supplied. The generic default plan is
        reordered so support discovery runs first, and the live reads that
        follow are dropped unless the ECU advertised them. If discovery cannot
        be decoded, every live request is skipped; the scanner never guesses at
        ECU capability.

        The whole plan runs inside one scheduler session so the adapter is
        opened, initialised and protocol-detected exactly once. Reopening the
        port between the two passes would reset the adapter mid-scan and make
        the first request of the second pass pay for protocol detection again.
        """

        if not adaptive:
            return self.scheduler.run(plan, stop_check=stop_check), None

        discovery = DiagnosticRequest(Operation.SUPPORTED_PIDS, 0x00)
        non_live = tuple(
            request
            for request in plan
            if request.operation not in {Operation.SUPPORTED_PIDS, Operation.LIVE_DATA}
        )
        live = tuple(request for request in plan if request.operation is Operation.LIVE_DATA)
        ordered = (discovery, *non_live, *live)

        state: dict[str, Any] = {"supported": None, "resolved": False}

        def keep(request: ValidatedRequest, results: tuple[ScanResult, ...]) -> bool:
            if request.operation is not Operation.LIVE_DATA:
                return True
            if not state["resolved"]:
                state["supported"] = self._supported_pids_from_results(results)
                state["resolved"] = True
            supported = state["supported"]
            return supported is not None and request.pid in supported

        report = self.scheduler.run(ordered, stop_check=stop_check, request_filter=keep)
        skip_reason = None
        if state["resolved"] and state["supported"] is None:
            skip_reason = (
                "Supported-PID discovery was unavailable; live PID requests were skipped."
            )
        return report, skip_reason

    @staticmethod
    def _supported_pids_from_results(results: tuple[ScanResult, ...]) -> frozenset[int] | None:
        for result in results:
            if result.operation is not Operation.SUPPORTED_PIDS:
                continue
            try:
                return decode_supported_pids_response(result.response)
            except (DecoderError, ValueError):
                return None
        return None

    @staticmethod
    def _new_session_id(started_at: datetime) -> str:
        stamp = started_at.astimezone().strftime("%Y%m%d-%H%M%S")
        return f"safescan-{stamp}-{uuid4().hex[:8]}"

    def _transport_metadata(self, plan_size: int) -> dict[str, Any]:
        transport = self.scheduler.transport
        metadata: dict[str, Any] = {
            "transport": type(transport).__name__,
            "scan_plan_requests": plan_size,
        }
        config = getattr(transport, "config", None)
        port = getattr(config, "port", None)
        if isinstance(port, str):
            metadata["port"] = port

        identity = getattr(transport, "adapter_identity", None)
        if isinstance(identity, bytes):
            metadata["adapter_identity"] = self._display_bytes(identity)
        identity_responses = getattr(transport, "identity_responses", None)
        if isinstance(identity_responses, dict):
            metadata["adapter_setup_responses"] = {
                str(command): self._display_bytes(response)
                for command, response in identity_responses.items()
                if isinstance(response, bytes)
            }
        return metadata

    @staticmethod
    def _display_bytes(value: bytes) -> str:
        text = value.decode("ascii", errors="replace").strip()
        if text and all(ord(char) >= 0x20 or char in "\t" for char in text):
            return text
        return value.hex(" ").upper()

    @staticmethod
    def _mark_decoded(session: DiagnosticSession, operation: Operation) -> None:
        """Record that an operation produced a decoded result.

        Downstream reports must be able to tell "the ECU reported nothing" from
        "this read never produced a usable response", so absence of evidence is
        never rendered as evidence of absence.
        """

        decoded = session.metadata.setdefault("decoded_operations", [])
        if isinstance(decoded, list) and operation.value not in decoded:
            decoded.append(operation.value)

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
            negative = decode_negative_response(result.response)
        except AdapterStatusResponse as status:
            session.notes.append(
                f"Adapter reported {status.status} for {result.operation.value}; "
                "no ECU data was returned."
            )
            return
        except DecoderError:
            negative = None
        if negative is not None:
            service, code = negative
            session.notes.append(
                f"ECU negative response for {result.operation.value}: "
                f"service 0x{service:02X}, code 0x{code:02X}."
            )
            return
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
                supported = decode_supported_pids_response(result.response)
                session.metadata["supported_pids"] = [
                    f"{pid:02X}" for pid in sorted(supported)
                ]
                requested = {
                    int(pid, 16)
                    for pid in session.metadata.get("requested_live_pids", [])
                    if isinstance(pid, str)
                }
                unsupported = sorted(requested - supported)
                if unsupported:
                    session.notes.append(
                        "Requested live PIDs not advertised by the ECU: "
                        + ", ".join(f"0x{pid:02X}" for pid in unsupported)
                        + "."
                    )
            self._mark_decoded(session, result.operation)
        except AdapterStatusResponse as status:
            session.notes.append(
                f"Adapter reported {status.status} for {result.operation.value}; "
                "no ECU data was returned."
            )
        except (DecoderError, ValueError) as exc:
            session.notes.append(
                f"Could not decode {result.operation.value} response: {exc}"
            )
