"""Render saved sessions without inventing missing values."""

from __future__ import annotations

import html
from pathlib import Path

from notescan.diagnostics.analyzer import analyze_session
from notescan.domain.models import DiagnosticSession, Finding


def _finding_lines(finding: Finding) -> list[str]:
    lines = [
        f"### {finding.severity.upper()}: {finding.title}",
        finding.message,
        f"Confidence: {finding.confidence}",
    ]
    if finding.evidence:
        lines.append("Evidence: " + "; ".join(finding.evidence))
    if finding.possible_causes:
        lines.append("Possible explanations: " + "; ".join(finding.possible_causes))
    return lines


def render_session_markdown(session: DiagnosticSession) -> str:
    """Create a portable report suitable for a mechanic or an issue attachment."""

    ended = session.ended_at.isoformat() if session.ended_at else "not recorded"
    status = "complete" if session.complete else "incomplete"
    lines = [
        "# SafeScan diagnostic evidence report",
        "",
        f"- Session ID: {session.session_id}",
        f"- Status: {status}",
        f"- Started: {session.started_at.isoformat()}",
        f"- Ended: {ended}",
        f"- Vehicle: {session.vehicle.display_name}",
        f"- Transmission: {session.vehicle.transmission}",
        f"- Adapter labels: {', '.join(session.vehicle.adapter_labels) or 'not recorded'}",
        "",
        "## Coverage",
        "",
        "Checked: " + (", ".join(session.supported_systems) or "none"),
        "",
        "Not checked: " + (", ".join(session.unsupported_systems) or "none recorded"),
        "",
        "## Trouble codes",
        "",
    ]
    if session.trouble_codes:
        lines.extend(
            f"- **{item.code}** ({item.status}, {item.ecu}): {item.description}"
            for item in session.trouble_codes
        )
    else:
        lines.append("- None reported in the preserved generic Mode 03 response.")
    lines.extend(["", "## Readiness", ""])
    if session.readiness:
        lines.append(f"- MIL on: {session.readiness.mil_on}")
        lines.append(f"- Stored code count: {session.readiness.stored_code_count}")
        for name, state in sorted(session.readiness.monitors.items()):
            lines.append(f"- {name}: {state}")
    else:
        lines.append("- Unavailable.")
    lines.extend(
        [
            "",
            "## Measurements",
            "",
            "| Time | PID | Observation | Value | ECU |",
            "|---|---|---:|---:|---|",
        ]
    )
    for item in sorted(session.measurements, key=lambda value: value.timestamp):
        lines.append(
            f"| {item.timestamp.isoformat()} | {item.pid} | {item.name} | "
            f"{item.value:.3f} {item.unit} | {item.ecu} |"
        )
    if not session.measurements:
        lines.append("| — | — | No decoded measurements | unavailable | — |")
    lines.extend(["", "## Observations", ""])
    findings = analyze_session(session)
    for finding in findings:
        lines.extend(_finding_lines(finding))
        lines.append("")
    lines.extend(
        [
            "## Evidence policy",
            "",
            "This report preserves observed data and reports coverage limits. "
            "A trouble code or pattern does not identify a failed part. "
            "No write, clear, actuator, relearn, coding, or reflashing operation is represented.",
            "",
        ]
    )
    return "\n".join(lines)


def render_session_html(session: DiagnosticSession) -> str:
    """Create a self-contained, printable HTML report."""

    markdown = render_session_markdown(session)
    body = html.escape(markdown).replace("\n", "<br>\n")
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>SafeScan evidence report</title>"
        "<style>body{font:15px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;"
        "color:#19324a}br{line-height:1.65}</style></head>"
        f"<body><pre style=\"white-space:pre-wrap\">{body}</pre></body></html>"
    )


def write_report(
    session: DiagnosticSession,
    destination: str | Path,
    *,
    format: str = "md",
) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if format.lower() in {"html", "htm"}:
        content = render_session_html(session)
    elif format.lower() in {"md", "markdown"}:
        content = render_session_markdown(session)
    else:
        raise ValueError("format must be 'md' or 'html'")
    target.write_text(content, encoding="utf-8")
    return target
