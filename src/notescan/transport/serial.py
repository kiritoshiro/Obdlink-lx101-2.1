"""Bounded Windows serial transport for a paired OBDLink LX adapter.

The adapter exposes a Classic Bluetooth serial COM port after Windows pairing.
This transport accepts only the generic read payloads allow-listed by the
policy; it has no method for clearing codes, writing an ECU, or sending an
arbitrary command. Adapter setup uses a fixed, harmless ELM327-compatible
sequence and never starts a vehicle request by itself.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any, Protocol, cast

from notescan.safety.errors import PolicyViolation, TransportError
from notescan.safety.policy import (
    FREEZE_FRAME_PIDS,
    LIVE_DATA_PIDS,
    SUPPORTED_PID_BASES,
)


class SerialPort(Protocol):
    """Small pyserial surface used by the transport and its offline tests."""

    timeout: float | None

    def close(self) -> None: ...

    def open(self) -> None: ...

    def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def reset_output_buffer(self) -> None: ...

    def write(self, data: bytes) -> int: ...


SerialFactory = Callable[..., SerialPort]


def _default_serial_factory(**kwargs: Any) -> SerialPort:
    try:
        import serial
    except ImportError as exc:  # pragma: no cover - dependency is runtime-required
        raise TransportError("pyserial is required for live adapter communication") from exc
    return cast(SerialPort, serial.Serial(**kwargs))


@dataclass(frozen=True, slots=True)
class SerialConfig:
    """Connection and framing limits for a paired Bluetooth serial port."""

    port: str
    baudrate: int = 115200
    open_timeout_s: float = 12.0
    command_timeout_s: float = 2.0
    max_response_bytes: int = 4096

    def __post_init__(self) -> None:
        if not re.fullmatch(r"(?:\\\\\.\\)?COM\d+", self.port, re.IGNORECASE):
            raise ValueError("port must be a Windows COM port such as COM7")
        if isinstance(self.baudrate, bool) or self.baudrate < 1:
            raise ValueError("baudrate must be positive")
        if self.open_timeout_s <= 0 or self.command_timeout_s <= 0:
            raise ValueError("serial timeouts must be positive")
        if self.max_response_bytes < 32:
            raise ValueError("max_response_bytes is too small")


_ADAPTER_COMMANDS = (
    "ATZ",
    "ATE0",
    "ATL0",
    "ATS1",
    "ATH0",
    "ATSP0",
    "ATI",
    "STDI",
    "STI",
    "STMFR",
)
_LIVE_READ_PIDS = LIVE_DATA_PIDS | SUPPORTED_PID_BASES | {0x01}


class SerialTransport:
    """Read-only ELM327-compatible transport for a Windows COM port.

    ``serial_factory`` is injectable so every behavior can be tested without
    Bluetooth, an adapter, or a vehicle. The transport opens one port, sends a
    fixed adapter-only setup, then exchanges allow-listed OBD reads until the
    caller closes it.
    """

    def __init__(
        self,
        config: SerialConfig,
        *,
        serial_factory: SerialFactory = _default_serial_factory,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config
        self._serial_factory = serial_factory
        self._clock = clock
        self._serial: SerialPort | None = None
        self._identity: bytes | None = None
        self._identity_responses: dict[str, bytes] = {}

    @property
    def is_open(self) -> bool:
        return self._serial is not None

    @property
    def adapter_identity(self) -> bytes | None:
        """Raw ``ATI`` response captured during the last successful open."""

        return self._identity

    @property
    def identity_responses(self) -> dict[str, bytes]:
        """Raw responses for every fixed identity command, keyed by command."""

        return dict(self._identity_responses)

    def open(self) -> None:
        if self._serial is not None:
            raise TransportError("serial transport is already open")
        try:
            port = self._serial_factory(
                port=self.config.port,
                baudrate=self.config.baudrate,
                timeout=self.config.command_timeout_s,
                write_timeout=self.config.command_timeout_s,
                exclusive=False,
            )
            if not getattr(port, "is_open", True):
                port.open()
            self._serial = port
            self._identity_responses = {}
            port.reset_input_buffer()
            port.reset_output_buffer()
            started = self._clock()
            for command in _ADAPTER_COMMANDS:
                remaining = self.config.open_timeout_s - (self._clock() - started)
                if remaining <= 0:
                    raise TransportError("adapter initialisation exceeded its time budget")
                response = self._adapter_command(
                    command,
                    timeout_s=min(self.config.command_timeout_s, remaining),
                )
                self._identity_responses[command] = response
                if command == "ATI":
                    self._identity = response
        except Exception as exc:
            self.close()
            if isinstance(exc, TransportError):
                raise
            raise TransportError(f"could not open or initialise {self.config.port}: {exc}") from exc

    def close(self) -> None:
        port, self._serial = self._serial, None
        self._identity = None
        self._identity_responses = {}
        if port is not None:
            try:
                port.close()
            except Exception as exc:
                raise TransportError(f"could not close {self.config.port}: {exc}") from exc

    def exchange(self, request: bytes, timeout_s: float) -> bytes:
        """Send one policy-shaped OBD request and return its prompt-framed reply."""

        if self._serial is None:
            raise TransportError("serial transport is closed")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not self._is_allowlisted_request(request):
            raise PolicyViolation("serial transport accepts only allow-listed read requests")
        wire = request.hex().upper().encode("ascii") + b"\r"
        return self._exchange_wire(wire, timeout_s)

    def _adapter_command(self, command: str, *, timeout_s: float | None = None) -> bytes:
        if command not in _ADAPTER_COMMANDS:
            raise PolicyViolation("adapter command is not allow-listed")
        return self._exchange_wire(
            command.encode("ascii") + b"\r",
            timeout_s or self.config.command_timeout_s,
        )

    def _exchange_wire(self, wire: bytes, timeout_s: float) -> bytes:
        port = self._serial
        if port is None:
            raise TransportError("serial transport is closed")
        try:
            port.reset_input_buffer()
            written = port.write(wire)
            if written != len(wire):
                raise TransportError("serial port accepted only part of the request")
            raw = bytearray()
            prompt_seen = False
            deadline = self._clock() + timeout_s
            while self._clock() < deadline and len(raw) < self.config.max_response_bytes:
                remaining = max(0.01, deadline - self._clock())
                port.timeout = min(self.config.command_timeout_s, remaining)
                chunk = port.read_until(b">")
                if chunk:
                    raw.extend(chunk)
                    if b">" in chunk:
                        prompt_seen = True
                        break
                else:
                    break
            if not raw:
                raise TransportError("adapter returned no response before timeout")
            if not prompt_seen:
                raise TransportError("adapter did not return its prompt before timeout")
            if len(raw) > self.config.max_response_bytes:
                raise TransportError("adapter response exceeded configured size limit")
            return bytes(raw).replace(b">", b"").strip()
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError(f"serial exchange failed: {exc}") from exc

    @staticmethod
    def _is_allowlisted_request(request: bytes) -> bool:
        if not isinstance(request, bytes) or not request:
            return False
        service = request[0]
        if service in {0x03, 0x07, 0x0A}:
            return len(request) == 1
        if len(request) != 2:
            return False
        pid = request[1]
        if service == 0x01:
            return pid in _LIVE_READ_PIDS
        if service == 0x02:
            return pid in FREEZE_FRAME_PIDS
        return service == 0x09 and pid == 0x02
