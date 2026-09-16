"""Small Windows-friendly, offline session replay viewer.

PySide6 is optional at import time so decoders, storage and reports remain
usable in a minimal Python environment. The window only reads local session
files or a deterministic synthetic demo.
"""

from __future__ import annotations

import sys
from pathlib import Path

from notescan.diagnostics.analyzer import analyze_session
from notescan.diagnostics.simulator import build_demo_session
from notescan.domain.models import DiagnosticSession
from notescan.reports.render import write_report
from notescan.storage.json_store import SessionStore

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on machines without PySide6
    QT_AVAILABLE = False


if QT_AVAILABLE:

    class SessionViewer(QMainWindow):
        """Review preserved sessions; there are no live vehicle controls."""

        def __init__(
            self,
            sessions: list[DiagnosticSession],
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.sessions = sessions
            self.setWindowTitle("SafeScan · Offline evidence viewer")
            self.resize(1100, 720)
            self.setMinimumSize(850, 560)
            self._build_ui()
            self._populate_sessions()

        def _build_ui(self) -> None:
            menu = self.menuBar().addMenu("&File")
            export = QAction("Export &report…", self)
            export.triggered.connect(self._export_report)
            menu.addAction(export)
            close = QAction("&Quit", self)
            close.triggered.connect(self.close)
            menu.addAction(close)

            root = QWidget()
            outer = QVBoxLayout(root)
            outer.setContentsMargins(18, 16, 18, 16)
            header = QHBoxLayout()
            title = QLabel("SafeScan")
            title.setStyleSheet("font-size: 25px; font-weight: 700; color: #17324D;")
            subtitle = QLabel("Read-only diagnostic evidence · offline replay")
            subtitle.setStyleSheet("font-size: 14px; color: #5D7184;")
            header.addWidget(title)
            header.addWidget(subtitle)
            header.addStretch()
            self.export_button = QPushButton("Export report")
            self.export_button.setToolTip("Save a Markdown or HTML copy of the selected evidence")
            self.export_button.clicked.connect(self._export_report)
            header.addWidget(self.export_button)
            outer.addLayout(header)

            self.coverage = QLabel()
            self.coverage.setWordWrap(True)
            self.coverage.setStyleSheet(
                "background:#EAF4F1; border:1px solid #B9D8CF; border-radius:8px; "
                "padding:10px; color:#214B47;"
            )
            outer.addWidget(self.coverage)

            splitter = QSplitter(Qt.Orientation.Horizontal)
            self.session_list = QListWidget()
            self.session_list.setAccessibleName("Saved diagnostic sessions")
            self.session_list.setMinimumWidth(210)
            self.session_list.currentRowChanged.connect(self._select_session)
            splitter.addWidget(self.session_list)

            details = QWidget()
            details_layout = QVBoxLayout(details)
            details_layout.setContentsMargins(12, 0, 0, 0)
            self.session_title = QLabel()
            self.session_title.setStyleSheet("font-size:18px;font-weight:600;color:#17324D;")
            details_layout.addWidget(self.session_title)
            self.tabs = QTabWidget()
            self.measurements = QTableWidget(0, 5)
            self.measurements.setHorizontalHeaderLabels(
                ["Time", "PID", "Observation", "Value", "Source"]
            )
            self.measurements.setAlternatingRowColors(True)
            self.measurements.setSortingEnabled(True)
            self.measurements.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.measurements.horizontalHeader().setStretchLastSection(True)
            self.tabs.addTab(self.measurements, "Measurements")
            self.codes = QTableWidget(0, 4)
            self.codes.setHorizontalHeaderLabels(["Code", "Status", "ECU", "Description"])
            self.codes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.codes.horizontalHeader().setStretchLastSection(True)
            self.tabs.addTab(self.codes, "Trouble codes")
            self.findings = QTextEdit()
            self.findings.setReadOnly(True)
            self.findings.setAccessibleName("Conservative observations")
            self.tabs.addTab(self.findings, "Observations")
            details_layout.addWidget(self.tabs)
            splitter.addWidget(details)
            splitter.setSizes([250, 800])
            outer.addWidget(splitter, 1)

            self.status = QLabel("Select a preserved session to replay it.")
            self.status.setStyleSheet("color:#5D7184;")
            outer.addWidget(self.status)
            self.setCentralWidget(root)

        def _populate_sessions(self) -> None:
            self.session_list.clear()
            for session in self.sessions:
                state = "complete" if session.complete else "incomplete"
                self.session_list.addItem(f"{session.session_id} · {state}")
            if self.sessions:
                self.session_list.setCurrentRow(0)

        def _select_session(self, row: int) -> None:
            if row < 0 or row >= len(self.sessions):
                return
            session = self.sessions[row]
            self.session_title.setText(f"{session.vehicle.display_name} · {session.session_id}")
            self.coverage.setText(
                f"Checked: {', '.join(session.supported_systems) or 'none'}   |   "
                f"Not checked: {', '.join(session.unsupported_systems) or 'none recorded'}"
            )
            self.measurements.setSortingEnabled(False)
            self.measurements.setRowCount(len(session.measurements))
            for index, measurement in enumerate(
                sorted(session.measurements, key=lambda item: item.timestamp)
            ):
                measurement_values = (
                    measurement.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    measurement.pid,
                    measurement.name,
                    f"{measurement.value:.3f} {measurement.unit}",
                    measurement.source,
                )
                for column, value in enumerate(measurement_values):
                    self.measurements.setItem(index, column, QTableWidgetItem(value))
            self.measurements.resizeColumnsToContents()
            self.measurements.setSortingEnabled(True)

            self.codes.setRowCount(len(session.trouble_codes))
            for index, trouble_code in enumerate(session.trouble_codes):
                code_values = (
                    trouble_code.code,
                    trouble_code.status,
                    trouble_code.ecu,
                    trouble_code.description,
                )
                for column, value in enumerate(code_values):
                    self.codes.setItem(index, column, QTableWidgetItem(value))
            self.codes.resizeColumnsToContents()

            blocks: list[str] = []
            for finding in analyze_session(session):
                blocks.append(
                    f"[{finding.severity.upper()}] {finding.title}\n"
                    f"{finding.message}\n"
                    f"Evidence: {'; '.join(finding.evidence) or 'unavailable'}\n"
                    f"Confidence: {finding.confidence}"
                )
            self.findings.setPlainText("\n\n".join(blocks))
            self.status.setText(
                f"{len(session.measurements)} measurements · "
                f"{len(session.trouble_codes)} stored codes · local replay only"
            )

        def _selected(self) -> DiagnosticSession | None:
            row = self.session_list.currentRow()
            return self.sessions[row] if 0 <= row < len(self.sessions) else None

        def _export_report(self) -> None:
            session = self._selected()
            if session is None:
                QMessageBox.information(
                    self,
                    "No session selected",
                    "Select a session before exporting.",
                )
                return
            target, selected_filter = QFileDialog.getSaveFileName(
                self,
                "Export evidence report",
                f"{session.session_id}.md",
                "Markdown (*.md);;HTML (*.html)",
            )
            if not target:
                return
            format_name = "html" if "HTML" in selected_filter else "md"
            try:
                write_report(session, target, format=format_name)
            except OSError as exc:
                QMessageBox.critical(self, "Export failed", str(exc))
                return
            self.status.setText(f"Report saved: {Path(target).name}")


def run(storage_root: str | Path | None = None) -> int:
    """Launch the viewer using local JSON sessions, or a synthetic demo."""

    if not QT_AVAILABLE:
        raise RuntimeError(
            "PySide6 is required for the desktop viewer; data tools remain available offline."
        )
    app = QApplication.instance() or QApplication(sys.argv)
    sessions: list[DiagnosticSession] = []
    if storage_root is not None:
        sessions = SessionStore(storage_root).list_sessions()
    if not sessions:
        sessions = [build_demo_session()]
    window = SessionViewer(sessions)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
