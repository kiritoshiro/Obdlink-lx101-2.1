"""Small, serialisable records used by SafeScan.

These models are deliberately transport agnostic.  A session can be created
from a live, reviewed read-only adapter in a later milestone, but the model
itself cannot issue commands or mutate a vehicle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


@dataclass(slots=True)
class VehicleProfile:
    """Known vehicle facts, with unknown fields left empty for verification."""

    make: str = "Nissan"
    model: str = "Note"
    generation: str = "E11"
    year: int | None = 2011
    engine: str = "1.4 petrol"
    power_kw: float | None = 65.0
    transmission: str = "Manual"
    fuel: str = "Petrol"
    adapter_labels: tuple[str, ...] = ("OBDLink LX", "LX101 2.1")
    vin: str | None = None
    market: str | None = None
    trim: str | None = None
    engine_code: str | None = None
    ecu_identifier: str | None = None
    mileage_km: int | None = None
    notes: str = "Facts supplied in chat; remaining fields require verification."

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["adapter_labels"] = list(self.adapter_labels)
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VehicleProfile:
        values = dict(data)
        if "adapter_labels" in values:
            values["adapter_labels"] = tuple(values["adapter_labels"] or ())
        return cls(**values)

    @property
    def display_name(self) -> str:
        year = f"{self.year} " if self.year else ""
        return f"{year}{self.make} {self.model} {self.engine}".strip()


@dataclass(slots=True)
class Measurement:
    """One timestamped numeric observation from a named ECU."""

    pid: str
    name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=utc_now)
    ecu: str = "engine"
    source: str = "synthetic"
    raw: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["timestamp"] = _iso(self.timestamp)
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Measurement:
        values = dict(data)
        values["timestamp"] = _parse_datetime(values.get("timestamp")) or utc_now()
        return cls(**values)


@dataclass(slots=True)
class TroubleCode:
    code: str
    description: str = "Description unavailable"
    status: str = "stored"
    ecu: str = "engine"
    raw: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TroubleCode:
        return cls(**dict(data))


@dataclass(slots=True)
class ReadinessStatus:
    """Emissions-monitor readiness as reported by Mode 01 PID 01."""

    mil_on: bool | None = None
    stored_code_count: int | None = None
    monitors: dict[str, str] = field(default_factory=dict)
    supported: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReadinessStatus:
        return cls(**dict(data))


@dataclass(slots=True)
class Finding:
    """Conservative interpretation output linked to observed evidence."""

    title: str
    severity: str
    message: str
    evidence: tuple[str, ...] = ()
    possible_causes: tuple[str, ...] = ()
    confidence: str = "low"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = list(self.evidence)
        result["possible_causes"] = list(self.possible_causes)
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Finding:
        values = dict(data)
        values["evidence"] = tuple(values.get("evidence", ()))
        values["possible_causes"] = tuple(values.get("possible_causes", ()))
        return cls(**values)


@dataclass(slots=True)
class DiagnosticSession:
    """Evidence-preserving session that can be saved and replayed offline."""

    session_id: str
    vehicle: VehicleProfile = field(default_factory=VehicleProfile)
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    complete: bool = False
    measurements: list[Measurement] = field(default_factory=list)
    trouble_codes: list[TroubleCode] = field(default_factory=list)
    readiness: ReadinessStatus | None = None
    supported_systems: tuple[str, ...] = ("engine/emissions",)
    unsupported_systems: tuple[str, ...] = (
        "ABS",
        "airbag/SRS",
        "body control",
        "steering",
    )
    raw_frames: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "vehicle": self.vehicle.to_dict(),
            "started_at": _iso(self.started_at),
            "ended_at": _iso(self.ended_at) if self.ended_at else None,
            "complete": self.complete,
            "measurements": [item.to_dict() for item in self.measurements],
            "trouble_codes": [item.to_dict() for item in self.trouble_codes],
            "readiness": self.readiness.to_dict() if self.readiness else None,
            "supported_systems": list(self.supported_systems),
            "unsupported_systems": list(self.unsupported_systems),
            "raw_frames": self.raw_frames,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DiagnosticSession:
        values = dict(data)
        values["vehicle"] = VehicleProfile.from_dict(values.get("vehicle", {}))
        values["started_at"] = _parse_datetime(values.get("started_at")) or utc_now()
        values["ended_at"] = _parse_datetime(values.get("ended_at"))
        values["measurements"] = [Measurement.from_dict(x) for x in values.get("measurements", [])]
        values["trouble_codes"] = [
            TroubleCode.from_dict(x) for x in values.get("trouble_codes", [])
        ]
        readiness = values.get("readiness")
        values["readiness"] = ReadinessStatus.from_dict(readiness) if readiness else None
        values["supported_systems"] = tuple(values.get("supported_systems", ()))
        values["unsupported_systems"] = tuple(values.get("unsupported_systems", ()))
        return cls(**values)

    @property
    def duration_seconds(self) -> float | None:
        if self.ended_at is None:
            return None
        return max(0.0, (self.ended_at - self.started_at).total_seconds())
