"""Typed, read-only OBD-II operations.

There is deliberately no constructor accepting an arbitrary command string or
an arbitrary service number.  Callers select an :class:`Operation` and, where
needed, one of the allow-listed PIDs.  The policy performs the final check
before an operation is encoded for transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import PolicyViolation


class Operation(str, Enum):
    """The finite set of operations SafeScan may request in this release."""

    SUPPORTED_PIDS = "supported_pids"
    LIVE_DATA = "live_data"
    FREEZE_FRAME = "freeze_frame"
    STORED_CODES = "stored_codes"
    PENDING_CODES = "pending_codes"
    PERMANENT_CODES = "permanent_codes"
    READINESS = "readiness"
    VEHICLE_IDENTIFICATION = "vehicle_identification"


@dataclass(frozen=True, slots=True)
class DiagnosticRequest:
    """A user-facing typed request.

    ``pid`` is required for PID operations and forbidden for whole-service
    code operations.  The request is immutable so it cannot be altered after
    policy validation.
    """

    operation: Operation
    pid: int | None = None


@dataclass(frozen=True, slots=True)
class ValidatedRequest:
    """An operation after policy validation, ready for deterministic encoding."""

    operation: Operation
    service: int
    pid: int | None = None


def encode_request(request: ValidatedRequest) -> bytes:
    """Encode a validated operation as an OBD request payload.

    Transport framing (ELM line endings, ISO-TP, or adapter-specific framing)
    belongs to the transport implementation.  This function only emits the
    exact service/PID bytes that the policy approved.
    """

    if not 0 <= request.service <= 0xFF:
        raise PolicyViolation("validated service is outside one-byte range")
    if request.pid is None:
        return bytes((request.service,))
    if not 0 <= request.pid <= 0xFF:
        raise PolicyViolation("validated PID is outside one-byte range")
    return bytes((request.service, request.pid))
