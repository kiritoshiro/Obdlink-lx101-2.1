"""Transport interface.

The interface is deliberately smaller than a general serial/CAN API: callers
can only exchange already-policy-validated request bytes and receive bytes.
No raw-command or write method exists here.
"""

from __future__ import annotations

from typing import Protocol


class DiagnosticTransport(Protocol):
    """Minimal lifecycle needed by the bounded scanner."""

    def open(self) -> None: ...

    def close(self) -> None: ...

    def exchange(self, request: bytes, timeout_s: float) -> bytes: ...
