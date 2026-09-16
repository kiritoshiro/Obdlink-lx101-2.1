"""Conservative checks over recorded observations.

The analyzer reports patterns and missing evidence. It never names a failed
part, and it cannot send or request anything from a vehicle.
"""

from __future__ import annotations

from collections import defaultdict

from notescan.domain.models import DiagnosticSession, Finding, Measurement


def _by_name(session: DiagnosticSession) -> dict[str, list[Measurement]]:
    grouped: dict[str, list[Measurement]] = defaultdict(list)
    for measurement in session.measurements:
        grouped[measurement.name].append(measurement)
    return grouped


def _average(items: list[Measurement]) -> float | None:
    return sum(item.value for item in items) / len(items) if items else None


def analyze_session(session: DiagnosticSession) -> list[Finding]:
    findings: list[Finding] = []
    grouped = _by_name(session)
    if not session.complete:
        findings.append(
            Finding(
                title="Session incomplete",
                severity="info",
                message="The recording ended before all planned observations were confirmed.",
                evidence=(f"{len(session.measurements)} measurements preserved",),
                confidence="high",
            )
        )

    if session.unsupported_systems:
        findings.append(
            Finding(
                title="Coverage is limited",
                severity="info",
                message=(
                    "This session covers generic engine/emissions evidence only. "
                    "The following systems were not checked: "
                    + ", ".join(session.unsupported_systems)
                    + "."
                ),
                evidence=tuple(session.supported_systems),
                confidence="high",
            )
        )

    if session.trouble_codes:
        for dtc in session.trouble_codes:
            findings.append(
                Finding(
                    title=f"Stored code {dtc.code}",
                    severity="warning",
                    message=(
                        f"{dtc.code} was reported by the {dtc.ecu} ECU. "
                        "A code identifies a monitored condition; it does not prove "
                        "which part failed."
                    ),
                    evidence=(dtc.description, f"status: {dtc.status}"),
                    possible_causes=(
                        "The monitored condition may be active, intermittent, or historical.",
                    ),
                    confidence="high",
                )
            )
    else:
        findings.append(
            Finding(
                title="No stored generic engine codes",
                severity="ok",
                message=(
                    "No stored generic engine/emissions trouble codes were present "
                    "in this session."
                ),
                evidence=("Mode 03 response contained no non-zero code records.",),
                confidence="medium",
            )
        )

    if session.readiness:
        not_ready = [
            name for name, state in session.readiness.monitors.items() if state == "not_ready"
        ]
        if not_ready:
            findings.append(
                Finding(
                    title="Readiness monitors not complete",
                    severity="caution",
                    message="Some emissions monitors have not completed their drive-cycle checks.",
                    evidence=tuple(not_ready),
                    possible_causes=(
                        "Recent battery disconnection or code clearing can reset monitors.",
                    ),
                    confidence="high",
                )
            )

    coolant = _average(grouped.get("Coolant temperature", []))
    short_trim = _average(grouped.get("Short-term fuel trim", []))
    long_trim = _average(grouped.get("Long-term fuel trim", []))
    if coolant is not None and coolant >= 70 and (short_trim is not None or long_trim is not None):
        combined = (short_trim or 0.0) + (long_trim or 0.0)
        if abs(combined) >= 10:
            direction = "positive" if combined > 0 else "negative"
            findings.append(
                Finding(
                    title="Fuel correction is elevated at warm observation",
                    severity="caution",
                    message=(
                        f"Average combined fuel correction is {combined:.1f}% during "
                        f"observations averaging {coolant:.1f}°C coolant temperature "
                        f"({direction}). "
                        "This is a pattern to investigate, not a component diagnosis."
                    ),
                    evidence=tuple(
                        value
                        for value in (
                            f"short-term: {short_trim:.1f}%" if short_trim is not None else None,
                            f"long-term: {long_trim:.1f}%" if long_trim is not None else None,
                        )
                        if value
                    ),
                    possible_causes=(
                        "Intake air leakage",
                        "Airflow or oxygen-sensor measurement bias",
                        "Fuel delivery or exhaust leak conditions",
                    ),
                    confidence="low",
                )
            )

    if not session.measurements:
        findings.append(
            Finding(
                title="No live measurements",
                severity="caution",
                message="The session contains no decoded live measurements to interpret.",
                evidence=("Only session metadata was preserved.",),
                confidence="high",
            )
        )
    return findings
