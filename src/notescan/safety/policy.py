"""Default-deny policy for SafeScan requests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .errors import PolicyViolation
from .operations import DiagnosticRequest, Operation, ValidatedRequest

# These are standard OBD-II reads with stable, public encodings.  Nissan
# enhanced services are intentionally absent until each one has a verified ECU
# target and a tested decoder.
LIVE_DATA_PIDS = frozenset(
    {
        0x05,  # engine coolant temperature
        0x06,  # short-term fuel trim, bank 1
        0x07,  # long-term fuel trim, bank 1
        0x0B,  # intake manifold absolute pressure
        0x0C,  # engine RPM
        0x0D,  # vehicle speed
        0x0F,  # intake air temperature
        0x10,  # mass air flow
        0x11,  # throttle position
        0x1F,  # run time since engine start
        0x2F,  # fuel level input
        0x46,  # ambient air temperature
        0x5C,  # engine oil temperature
    }
)
SUPPORTED_PID_BASES = frozenset({0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0})
FREEZE_FRAME_PIDS = LIVE_DATA_PIDS


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    """Read-only allow-list and finite session budget.

    Validation is intentionally strict.  Adding an operation requires a code
    change and tests, which makes an accidental write or unsupported request
    fail closed.
    """

    max_requests_per_session: int = 64

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_requests_per_session, bool)
            or not isinstance(self.max_requests_per_session, int)
            or self.max_requests_per_session < 1
        ):
            raise ValueError("max_requests_per_session must be a positive integer")

    def validate(self, request: DiagnosticRequest) -> ValidatedRequest:
        """Validate one typed request and return its safe wire representation."""

        if not isinstance(request, DiagnosticRequest):
            raise PolicyViolation("only DiagnosticRequest values are accepted")
        if not isinstance(request.operation, Operation):
            raise PolicyViolation("unknown operation; policy is default-deny")
        if request.pid is not None and (
            isinstance(request.pid, bool)
            or not isinstance(request.pid, int)
            or not 0 <= request.pid <= 0xFF
        ):
            raise PolicyViolation("PID must be an integer from 0x00 to 0xFF")

        operation = request.operation
        if operation is Operation.SUPPORTED_PIDS:
            self._require_pid(request, SUPPORTED_PID_BASES, "supported PID base")
            return ValidatedRequest(operation, 0x01, request.pid)
        if operation is Operation.LIVE_DATA:
            self._require_pid(request, LIVE_DATA_PIDS, "live-data PID")
            return ValidatedRequest(operation, 0x01, request.pid)
        if operation is Operation.FREEZE_FRAME:
            self._require_pid(request, FREEZE_FRAME_PIDS, "freeze-frame PID")
            return ValidatedRequest(operation, 0x02, request.pid)
        if operation is Operation.READINESS:
            self._require_no_pid(request)
            # Mode 01 PID 01 contains monitor readiness and MIL status.
            return ValidatedRequest(operation, 0x01, 0x01)
        if operation is Operation.STORED_CODES:
            self._require_no_pid(request)
            return ValidatedRequest(operation, 0x03)
        if operation is Operation.PENDING_CODES:
            self._require_no_pid(request)
            return ValidatedRequest(operation, 0x07)
        if operation is Operation.PERMANENT_CODES:
            self._require_no_pid(request)
            return ValidatedRequest(operation, 0x0A)
        if operation is Operation.VEHICLE_IDENTIFICATION:
            self._require_no_pid(request)
            # Mode 09 PID 02 is the standard VIN read.
            return ValidatedRequest(operation, 0x09, 0x02)
        raise PolicyViolation("operation is not approved by this policy")

    def validate_batch(self, requests: Iterable[DiagnosticRequest]) -> tuple[ValidatedRequest, ...]:
        """Validate every request before any transport I/O begins."""

        materialized = tuple(requests)
        if len(materialized) > self.max_requests_per_session:
            raise PolicyViolation(
                f"scan contains {len(materialized)} requests; limit is "
                f"{self.max_requests_per_session}"
            )
        return tuple(self.validate(request) for request in materialized)

    @staticmethod
    def _require_pid(request: DiagnosticRequest, allowed: frozenset[int], label: str) -> None:
        if request.pid is None:
            raise PolicyViolation(f"{request.operation.value} requires a {label}")
        if request.pid not in allowed:
            raise PolicyViolation(
                f"PID 0x{request.pid:02X} is not approved for {request.operation.value}"
            )

    @staticmethod
    def _require_no_pid(request: DiagnosticRequest) -> None:
        if request.pid is not None:
            raise PolicyViolation(f"{request.operation.value} does not accept a PID")
