"""Deterministic fake/replay transports for offline development and testing."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from time import sleep

from notescan.safety.errors import ReplayMismatch, TransportError


@dataclass(frozen=True, slots=True)
class ReplayExchange:
    """One expected request and its recorded response."""

    request: bytes
    response: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.request, bytes) or not isinstance(self.response, bytes):
            raise TypeError("replay request and response must be bytes")


class ReplayTransport:
    """Offline transport that replays a finite, ordered capture.

    The transport fails on an unexpected request, a request after exhaustion,
    or an invalid timeout.  This catches policy/encoding regressions without
    requiring an adapter or a vehicle.
    """

    def __init__(self, exchanges: Iterable[ReplayExchange], *, latency_s: float = 0.0) -> None:
        if latency_s < 0:
            raise ValueError("latency_s cannot be negative")
        self._exchanges = tuple(exchanges)
        self._latency_s = latency_s
        self._index = 0
        self._open = False
        self.requests: list[bytes] = []

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def remaining(self) -> int:
        return len(self._exchanges) - self._index

    def open(self) -> None:
        if self._open:
            raise TransportError("transport is already open")
        self._open = True

    def close(self) -> None:
        self._open = False

    def exchange(self, request: bytes, timeout_s: float) -> bytes:
        if not self._open:
            raise TransportError("transport is closed")
        if not isinstance(request, bytes):
            raise TypeError("request must be bytes")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self._index >= len(self._exchanges):
            raise ReplayMismatch("replay has no response for this request")
        if self._latency_s > timeout_s:
            sleep(timeout_s)
            raise TransportError("replay response exceeded request timeout")
        if self._latency_s:
            sleep(self._latency_s)
        expected = self._exchanges[self._index]
        if expected.request != request:
            raise ReplayMismatch(
                f"replay request mismatch at index {self._index}: "
                f"expected {expected.request.hex(' ')}, got {request.hex(' ')}"
            )
        self._index += 1
        self.requests.append(request)
        return expected.response


class FakeTransport:
    """Small programmable offline transport for UI and integration tests."""

    def __init__(
        self,
        responses: Mapping[bytes, bytes] | Callable[[bytes], bytes] | None = None,
    ) -> None:
        self._responses = responses or {}
        self._open = False
        self.requests: list[bytes] = []

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        if self._open:
            raise TransportError("transport is already open")
        self._open = True

    def close(self) -> None:
        self._open = False

    def exchange(self, request: bytes, timeout_s: float) -> bytes:
        if not self._open:
            raise TransportError("transport is closed")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.requests.append(request)
        if callable(self._responses):
            response = self._responses(request)
        else:
            try:
                response = self._responses[request]
            except KeyError as exc:
                raise TransportError(f"fake has no response for {request.hex(' ')}") from exc
        if not isinstance(response, bytes):
            raise TransportError("fake response must be bytes")
        return response
