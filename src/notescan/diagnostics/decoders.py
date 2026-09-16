"""Strict, side-effect-free OBD-II response decoders.

Only common generic Mode 01 PIDs are decoded here. Nissan-specific commands
and all write/clear/actuator operations deliberately have no representation
in this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from notescan.domain.models import Measurement, ReadinessStatus, TroubleCode, utc_now


class DecoderError(ValueError):
    """A response was malformed or used an unexpected service."""


class UnsupportedPidError(DecoderError):
    """The generic decoder does not claim support for this PID."""


def parse_hex_bytes(value: str | bytes | bytearray | Iterable[int]) -> bytes:
    """Parse a hex response while rejecting malformed or unsafe input."""

    if isinstance(value, bytes | bytearray):
        raw = bytes(value)
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            return raw
        if any(char.isspace() for char in text) or text.lower().startswith("0x"):
            value = text
        else:
            return raw
    if isinstance(value, str):
        text = value.replace(",", " ").replace(";", " ").strip()
        if not text:
            return b""
        tokens = text.split()
        try:
            if len(tokens) == 1 and len(tokens[0]) > 2 and not tokens[0].lower().startswith("0x"):
                token = tokens[0]
                if len(token) % 2:
                    raise ValueError
                return bytes.fromhex(token)
            return bytes(int(token, 16) for token in tokens)
        except ValueError as exc:
            raise DecoderError(f"Malformed hex response: {value!r}") from exc
    try:
        output = bytes(value)
    except (TypeError, ValueError) as exc:
        raise DecoderError("Response must be hex text or byte values") from exc
    if any(item < 0 or item > 255 for item in output):
        raise DecoderError("Response byte outside 0..255")
    return output


_PID_NAMES = {
    0x05: ("Coolant temperature", "°C", 1),
    0x06: ("Short-term fuel trim", "%", 1),
    0x07: ("Long-term fuel trim", "%", 1),
    0x0B: ("Intake manifold pressure", "kPa", 1),
    0x0C: ("Engine speed", "rpm", 2),
    0x0D: ("Vehicle speed", "km/h", 1),
    0x0F: ("Intake air temperature", "°C", 1),
    0x10: ("Mass air flow", "g/s", 2),
    0x11: ("Throttle position", "%", 1),
}


def _decode_pid(pid: int, payload: bytes) -> float:
    if pid in (0x05, 0x0F):
        return payload[0] - 40
    if pid in (0x06, 0x07):
        return (payload[0] - 128) * 100 / 128
    if pid == 0x0C:
        return ((payload[0] << 8) | payload[1]) / 4
    if pid == 0x10:
        return ((payload[0] << 8) | payload[1]) / 100
    if pid == 0x11:
        return payload[0] * 100 / 255
    return float(payload[0])


def decode_pid_response(
    response: str | bytes | bytearray | Iterable[int],
    *,
    timestamp: datetime | None = None,
    ecu: str = "engine",
    source: str = "recorded",
) -> Measurement:
    """Decode a positive Mode 01 response such as 41 0C 1A F8."""

    raw_bytes = parse_hex_bytes(response)
    if len(raw_bytes) < 3 or raw_bytes[0] != 0x41:
        raise DecoderError("Expected positive Mode 01 response (41 PID ...)")
    pid = raw_bytes[1]
    spec = _PID_NAMES.get(pid)
    if spec is None:
        raise UnsupportedPidError(f"Generic PID 0x{pid:02X} is not supported")
    name, unit, required = spec
    payload = raw_bytes[2:]
    if len(payload) < required:
        raise DecoderError(f"PID 0x{pid:02X} needs {required} data bytes")
    return Measurement(
        pid=f"01{pid:02X}",
        name=name,
        value=_decode_pid(pid, payload),
        unit=unit,
        timestamp=timestamp or utc_now(),
        ecu=ecu,
        source=source,
        raw=" ".join(f"{item:02X}" for item in raw_bytes),
    )


def decode_dtc_response(
    response: str | bytes | bytearray | Iterable[int],
    *,
    ecu: str = "engine",
    status: str = "stored",
) -> list[TroubleCode]:
    """Decode generic Mode 03 response bytes into DTC records."""

    raw_bytes = parse_hex_bytes(response)
    if not raw_bytes or raw_bytes[0] != 0x43:
        raise DecoderError("Expected positive Mode 03 response (43 ...)")
    if len(raw_bytes[1:]) % 2:
        raise DecoderError("DTC response must contain complete two-byte records")
    output: list[TroubleCode] = []
    type_letters = "PCBU"
    for index in range(1, len(raw_bytes), 2):
        first, second = raw_bytes[index : index + 2]
        if first == 0 and second == 0:
            continue
        letter = type_letters[(first >> 6) & 0x03]
        code = f"{letter}{(first >> 4) & 0x03}{first & 0x0F:X}{second:02X}"
        output.append(
            TroubleCode(
                code=code,
                description="Generic diagnostic code; consult service data.",
                status=status,
                ecu=ecu,
                raw=" ".join(f"{item:02X}" for item in raw_bytes[index : index + 2]),
            )
        )
    return output


def decode_readiness_response(
    response: str | bytes | bytearray | Iterable[int],
) -> ReadinessStatus:
    """Decode Mode 01 PID 01 MIL, code count and monitor readiness bits."""

    raw_bytes = parse_hex_bytes(response)
    if len(raw_bytes) < 5 or raw_bytes[:2] != bytes((0x41, 0x01)):
        raise DecoderError("Expected positive Mode 01 PID 01 response (41 01 ...)")
    first, supported, ready = raw_bytes[2:5]
    monitor_bits = (
        ("misfire", 0),
        ("fuel_system", 1),
        ("components", 2),
        ("catalyst", 3),
        ("heated_catalyst", 4),
        ("evaporative_system", 5),
        ("secondary_air", 6),
        ("oxygen_sensor", 7),
    )
    monitors = {
        name: ("ready" if ready & (1 << bit) == 0 else "not_ready")
        if supported & (1 << bit)
        else "unsupported"
        for name, bit in monitor_bits
    }
    return ReadinessStatus(
        mil_on=bool(first & 0x80),
        stored_code_count=first & 0x7F,
        monitors=monitors,
    )
