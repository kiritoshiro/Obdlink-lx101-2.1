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


class AdapterStatusResponse(DecoderError):
    """The adapter reported its own status instead of returning ECU data.

    ``NO DATA``, ``UNABLE TO CONNECT`` and similar ELM327 replies are real
    evidence about the exchange, not malformed input, so they are raised
    separately and recorded as such rather than as a decoder failure.
    """

    def __init__(self, status: str) -> None:
        super().__init__(f"Adapter reported {status!r} instead of an ECU response")
        self.status = status


# ELM327-compatible adapters interleave their own informational and error text
# with ECU responses.  ``SEARCHING...`` in particular precedes the first reply
# after protocol auto-detection, so it must not be mistaken for hex data.
_ADAPTER_NOISE_LINES = frozenset({"SEARCHING...", "SEARCHING"})
_ADAPTER_STATUS_LINES = frozenset(
    {
        "?",
        "BUFFER FULL",
        "BUS BUSY",
        "BUS ERROR",
        "CAN ERROR",
        "DATA ERROR",
        "ERROR",
        "FB ERROR",
        "LV RESET",
        "NO DATA",
        "STOPPED",
        "UNABLE TO CONNECT",
    }
)


def decode_supported_pids_response(
    response: str | bytes | bytearray | Iterable[int],
) -> frozenset[int]:
    """Decode a standard Mode 01 supported-PID bitmap response.

    A response such as ``41 00 BE 3E B8 13`` advertises PIDs 0x01 through
    0x20. The most-significant bitmap bit represents the first PID after the
    requested base; the least-significant bit represents the last one.
    """

    raw_bytes = parse_hex_bytes(response)
    if len(raw_bytes) < 6 or raw_bytes[0] != 0x41:
        raise DecoderError("Expected positive Mode 01 supported-PID response (41 base bitmap)")
    base = raw_bytes[1]
    if base not in {0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0}:
        raise DecoderError(f"Unsupported supported-PID base 0x{base:02X}")
    bitmap = int.from_bytes(raw_bytes[2:6], "big")
    return frozenset(
        base + offset
        for offset in range(1, 33)
        if bitmap & (1 << (32 - offset))
    )


def decode_negative_response(
    response: str | bytes | bytearray | Iterable[int],
) -> tuple[int, int] | None:
    """Return ``(requested_service, negative_response_code)`` when present."""

    raw_bytes = parse_hex_bytes(response)
    if len(raw_bytes) >= 3 and raw_bytes[0] == 0x7F:
        return raw_bytes[1], raw_bytes[2]
    return None


def _looks_like_hex_text(tokens: list[str]) -> bool:
    r"""Return ``True`` only for token lists an adapter would emit as hex text.

    Every token must be a complete, even-length run of hex digits.  Requiring
    even length is what separates real hex text from raw bytes that merely
    happen to decode as ASCII, such as ``b"\x41\x0c\x0d\x20"``.
    """

    return bool(tokens) and all(
        token and len(token) % 2 == 0 and all(char in "0123456789abcdefABCDEF" for char in token)
        for token in tokens
    )


def strip_adapter_noise(text: str) -> str:
    """Remove ELM327 informational lines and surface adapter status replies."""

    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    kept: list[str] = []
    statuses: list[str] = []
    for line in lines:
        if not line:
            continue
        upper = line.upper()
        if upper in _ADAPTER_NOISE_LINES:
            continue
        if upper in _ADAPTER_STATUS_LINES:
            statuses.append(upper)
            continue
        # ``SEARCHING...41 00 ...`` arrives without a separator on some adapters.
        for noise in sorted(_ADAPTER_NOISE_LINES, key=len, reverse=True):
            if upper.startswith(noise):
                line = line[len(noise) :].strip()
                break
        if line:
            kept.append(line)
    if not kept and statuses:
        raise AdapterStatusResponse(statuses[0])
    return " ".join(kept)


def parse_hex_bytes(value: str | bytes | bytearray | Iterable[int]) -> bytes:
    """Parse a hex response while rejecting malformed or unsafe input."""

    if isinstance(value, bytes | bytearray):
        raw = bytes(value)
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            return raw
        cleaned = strip_adapter_noise(text)
        if _looks_like_hex_text(cleaned.replace(",", " ").replace(";", " ").split()):
            value = cleaned
        else:
            return raw
    if isinstance(value, str):
        text = strip_adapter_noise(value).replace(",", " ").replace(";", " ").strip()
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


CONTINUOUS_MONITORS = (
    ("misfire", 0),
    ("fuel_system", 1),
    ("components", 2),
)
SPARK_IGNITION_MONITORS = (
    ("catalyst", 0),
    ("heated_catalyst", 1),
    ("evaporative_system", 2),
    ("secondary_air_system", 3),
    ("ac_refrigerant", 4),
    ("oxygen_sensor", 5),
    ("oxygen_sensor_heater", 6),
    ("egr_system", 7),
)
COMPRESSION_IGNITION_MONITORS = (
    ("nmhc_catalyst", 0),
    ("nox_scr_aftertreatment", 1),
    ("boost_pressure", 3),
    ("exhaust_gas_sensor", 5),
    ("particulate_filter", 6),
    ("egr_vvt_system", 7),
)


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
    0x1F: ("Runtime since engine start", "s", 2),
    0x2F: ("Fuel level", "%", 1),
    0x46: ("Ambient air temperature", "°C", 1),
    0x5C: ("Engine oil temperature", "°C", 1),
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
    if pid == 0x1F:
        return float((payload[0] << 8) | payload[1])
    if pid == 0x2F:
        return payload[0] * 100 / 255
    if pid in (0x46, 0x5C):
        return payload[0] - 40
    return float(payload[0])


def decode_pid_response(
    response: str | bytes | bytearray | Iterable[int],
    *,
    timestamp: datetime | None = None,
    ecu: str = "engine",
    source: str = "recorded",
    positive_service: int = 0x41,
) -> Measurement:
    """Decode a positive Mode 01/02 response such as ``41 0C 1A F8``."""

    raw_bytes = parse_hex_bytes(response)
    if not 0x40 <= positive_service <= 0x4F:
        raise ValueError("positive_service must be in the 0x40..0x4F range")
    if len(raw_bytes) < 3 or raw_bytes[0] != positive_service:
        raise DecoderError(
            f"Expected positive response ({positive_service:02X} PID ... )"
        )
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
    positive_service: int = 0x43,
) -> list[TroubleCode]:
    """Decode a positive generic DTC response into DTC records.

    ``positive_service`` is 0x43 for stored, 0x47 for pending, and 0x4A for
    permanent codes. Keeping it explicit prevents a response from one mode
    being silently labelled as another.

    On ISO 15765-4 (CAN) the response carries a DTC count byte between the
    service byte and the two-byte DTC records; on the older serial protocols it
    does not. The framing is detected from the payload length, because an
    unpadded record list always has an even length. A declared count larger
    than the records present is rejected rather than guessed at.
    """

    raw_bytes = parse_hex_bytes(response)
    if not 0x40 <= positive_service <= 0x4F:
        raise ValueError("positive_service must be in the 0x40..0x4F range")
    if not raw_bytes or raw_bytes[0] != positive_service:
        raise DecoderError(
            f"Expected positive DTC response ({positive_service:02X} ... )"
        )
    payload = raw_bytes[1:]
    declared_count: int | None = None
    if len(payload) % 2:
        declared_count = payload[0]
        payload = payload[1:]
        if declared_count > len(payload) // 2:
            raise DecoderError(
                f"DTC response declares {declared_count} codes but carries "
                f"{len(payload) // 2} records"
            )
    output: list[TroubleCode] = []
    type_letters = "PCBU"
    for index in range(0, len(payload), 2):
        first, second = payload[index : index + 2]
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
                raw=" ".join(f"{item:02X}" for item in payload[index : index + 2]),
            )
        )
    # Trailing 00 00 padding is normal, so fewer decoded codes than declared is
    # expected; more codes than declared means the framing was misread.
    if declared_count is not None and len(output) > declared_count:
        raise DecoderError(
            f"DTC response declares {declared_count} codes but decoded {len(output)}"
        )
    return output


def decode_vin_response(
    response: str | bytes | bytearray | Iterable[int],
) -> str:
    """Decode a standard Mode 09 PID 02 VIN response.

    ISO 15765 responses commonly include a one-byte frame count between the
    ``49 02`` header and the 17 ASCII VIN characters. The count is ignored;
    all remaining printable bytes are validated as one VIN.
    """

    raw_bytes = parse_hex_bytes(response)
    if len(raw_bytes) < 3 or raw_bytes[:2] != bytes((0x49, 0x02)):
        raise DecoderError("Expected positive Mode 09 PID 02 response (49 02 ...)")
    payload = raw_bytes[2:]
    if len(payload) >= 18 and payload[0] <= 0x0F:
        payload = payload[1:]
    try:
        vin = bytes(item for item in payload if 0x20 <= item <= 0x7E).decode("ascii")
    except UnicodeDecodeError as exc:
        raise DecoderError("VIN response contained non-ASCII bytes") from exc
    vin = vin.strip()
    if len(vin) != 17 or not vin.isalnum():
        raise DecoderError("VIN response did not contain exactly 17 alphanumeric characters")
    return vin


def decode_readiness_response(
    response: str | bytes | bytearray | Iterable[int],
) -> ReadinessStatus:
    """Decode Mode 01 PID 01 MIL, code count and monitor readiness bits.

    SAE J1979 splits the four data bytes as follows. Byte A carries the MIL
    lamp state and the stored-code count. Byte B carries the three continuous
    monitors: bits 0-2 say whether each is supported and bits 4-6 say whether
    it is *not* complete. Bytes C and D carry the eight non-continuous
    monitors, C for support and D for incompleteness. Bit 3 of byte B selects
    the compression-ignition monitor names instead of the spark-ignition ones.
    """

    raw_bytes = parse_hex_bytes(response)
    if len(raw_bytes) < 6 or raw_bytes[:2] != bytes((0x41, 0x01)):
        raise DecoderError("Expected positive Mode 01 PID 01 response (41 01 A B C D)")
    first, byte_b, supported, incomplete = raw_bytes[2:6]
    compression_ignition = bool(byte_b & 0x08)

    monitors: dict[str, str] = {}
    for name, bit in CONTINUOUS_MONITORS:
        if byte_b & (1 << bit):
            monitors[name] = "not_ready" if byte_b & (1 << (bit + 4)) else "ready"
        else:
            monitors[name] = "unsupported"

    names = (
        COMPRESSION_IGNITION_MONITORS if compression_ignition else SPARK_IGNITION_MONITORS
    )
    for name, bit in names:
        if supported & (1 << bit):
            monitors[name] = "not_ready" if incomplete & (1 << bit) else "ready"
        else:
            monitors[name] = "unsupported"

    return ReadinessStatus(
        mil_on=bool(first & 0x80),
        stored_code_count=first & 0x7F,
        monitors=monitors,
    )
