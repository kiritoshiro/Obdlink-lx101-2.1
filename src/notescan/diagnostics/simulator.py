"""Deterministic synthetic sessions for development and UI replay."""

from __future__ import annotations

from datetime import timedelta

from notescan.domain.models import (
    DiagnosticSession,
    Measurement,
    ReadinessStatus,
    VehicleProfile,
    utc_now,
)


def build_demo_session(session_id: str = "demo-warm-idle") -> DiagnosticSession:
    """Return a safe, offline-only session resembling a warm idle capture."""

    started = utc_now() - timedelta(minutes=3)
    session = DiagnosticSession(
        session_id=session_id,
        vehicle=VehicleProfile(),
        started_at=started,
        ended_at=started + timedelta(minutes=2),
        complete=True,
        readiness=ReadinessStatus(
            mil_on=False,
            stored_code_count=0,
            monitors={
                "misfire": "ready",
                "fuel_system": "ready",
                "components": "ready",
                "catalyst": "not_ready",
                "oxygen_sensor": "ready",
            },
        ),
        notes=["Synthetic replay data; no vehicle connection was made."],
    )
    rows = (
        ("0105", "Coolant temperature", 86.0, "°C"),
        ("010C", "Engine speed", 760.0, "rpm"),
        ("010B", "Intake manifold pressure", 34.0, "kPa"),
        ("010F", "Intake air temperature", 28.0, "°C"),
        ("0110", "Mass air flow", 3.7, "g/s"),
        ("0106", "Short-term fuel trim", 7.0, "%"),
        ("0107", "Long-term fuel trim", 5.0, "%"),
        ("0111", "Throttle position", 12.0, "%"),
    )
    for offset, (pid, name, value, unit) in enumerate(rows):
        session.measurements.append(
            Measurement(
                pid=pid,
                name=name,
                value=value,
                unit=unit,
                timestamp=started + timedelta(seconds=offset * 10),
                source="synthetic",
                raw="synthetic",
            )
        )
    session.raw_frames.extend(
        [
            {
                "timestamp": started.isoformat(),
                "request": "01 05",
                "response": "41 05 7E",
                "ecu": "engine",
            },
            {
                "timestamp": started.isoformat(),
                "request": "03",
                "response": "43 00 00",
                "ecu": "engine",
            },
        ]
    )
    return session
