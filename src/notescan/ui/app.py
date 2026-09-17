"""Small Windows-friendly, offline session replay viewer.

PySide6 is optional at import time so decoders, storage and reports remain
usable in a minimal Python environment. The window only reads local session
files or a deterministic synthetic demo.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import cast

from notescan.diagnostics.analyzer import analyze_session
from notescan.diagnostics.scanner import SafeScanner, ScanCapture
from notescan.diagnostics.simulator import build_demo_session
from notescan.domain.models import DiagnosticSession
from notescan.reports.render import write_report
from notescan.safety.scheduler import SafeScheduler
from notescan.storage.json_store import SessionStore
from notescan.transport import SerialConfig, SerialTransport

try:
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QAction, QCloseEvent
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QInputDialog,
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

    def default_storage_root() -> Path:
        """Return the per-user directory for live session evidence."""

        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / ".safescan"
        return base / "SafeScan" / "sessions"


    class ScanWorker(QThread):
        """Run one explicit live scan away from the Qt event loop."""

        completed = Signal(object)
        failed = Signal(str)

        def __init__(self, port: str, storage_root: Path, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.port = port
            self.storage_root = storage_root
            self._stop_requested = threading.Event()

        def request_stop(self) -> None:
            self._stop_requested.set()

        def run(self) -> None:  # pragma: no cover - exercised through a live Qt session
            try:
                transport = SerialTransport(SerialConfig(self.port))
                scanner = SafeScanner(
                    SafeScheduler(transport),
                    store=SessionStore(self.storage_root),
                )
                capture = scanner.run(stop_check=self._stop_requested.is_set)
            except Exception as exc:
                self.failed.emit(str(exc))
                return
            self.completed.emit(capture)

    class SessionViewer(QMainWindow):
        """Review preserved sessions and start explicit read-only live scans."""

        def __init__(
            self,
            sessions: list[DiagnosticSession],
            storage_root: Path | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.sessions = sessions
            self.storage_root = storage_root
            self._scan_worker: ScanWorker | None = None
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
            live_scan = QAction("Start &live read-only scan…", self)
            live_scan.triggered.connect(self._start_live_scan)
            menu.addAction(live_scan)
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
            self.live_button = QPushButton("Live scan…")
            self.live_button.setToolTip(
                "Connect to one already-paired Windows COM port and run the finite read-only plan"
            )
            self.live_button.clicked.connect(self._start_live_scan)
            header.addWidget(self.live_button)
            self.cancel_button = QPushButton("Stop scan")
            self.cancel_button.setToolTip("Stop after the current bounded request")
            self.cancel_button.clicked.connect(self._cancel_live_scan)
            self.cancel_button.setEnabled(False)
            header.addWidget(self.cancel_button)
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
            self.metadata_view = QTextEdit()
            self.metadata_view.setReadOnly(True)
            self.metadata_view.setAccessibleName("Session metadata")
            self.tabs.addTab(self.metadata_view, "Metadata")
            self.raw_frames = QTableWidget(0, 5)
            self.raw_frames.setHorizontalHeaderLabels(
                ["Time", "Operation", "Request", "Response", "Response bytes"]
            )
            self.raw_frames.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.raw_frames.setAlternatingRowColors(True)
            self.raw_frames.horizontalHeader().setStretchLastSection(True)
            self.tabs.addTab(self.raw_frames, "Raw frames")
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

            metadata_lines = [f"{key}: {value}" for key, value in sorted(session.metadata.items())]
            self.metadata_view.setPlainText("\n".join(metadata_lines) or "No metadata recorded.")

            self.raw_frames.setRowCount(len(session.raw_frames))
            for index, frame in enumerate(session.raw_frames):
                frame_values = (
                    str(frame.get("timestamp", "")),
                    str(frame.get("operation", "")),
                    str(frame.get("request", "")),
                    str(frame.get("response", "")),
                    str(frame.get("response_bytes", "")),
                )
                for column, value in enumerate(frame_values):
                    self.raw_frames.setItem(index, column, QTableWidgetItem(value))
            self.raw_frames.resizeColumnsToContents()

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

        def _start_live_scan(self) -> None:
            if self._scan_worker is not None:
                return
            port, accepted = QInputDialog.getText(
                self,
                "Paired OBDLink COM port",
                "Windows COM port (for example, COM7):",
                text="COM",
            )
            if not accepted:
                return
            try:
                config = SerialConfig(port.strip())
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid COM port", str(exc))
                return
            confirmation = QMessageBox.question(
                self,
                "Confirm stationary read-only scan",
                (
                    "Confirm the Nissan Note is safely parked with the ignition on, "
                    "the adapter already paired in Windows, and no other OBD app is connected.\n\n"
                    "SafeScan will send only the finite generic read-only plan."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation is not QMessageBox.StandardButton.Yes:
                return
            storage_root = self.storage_root or default_storage_root()
            self._scan_worker = ScanWorker(config.port, storage_root, self)
            self._scan_worker.completed.connect(self._live_scan_completed)
            self._scan_worker.failed.connect(self._live_scan_failed)
            self._set_scan_controls(running=True)
            self.status.setText(
                f"Connecting to {config.port}; stop is available at request boundaries…"
            )
            self._scan_worker.start()

        def _cancel_live_scan(self) -> None:
            if self._scan_worker is None:
                return
            self._scan_worker.request_stop()
            self.cancel_button.setEnabled(False)
            self.status.setText("Stopping after the current bounded request…")

        def _set_scan_controls(self, *, running: bool) -> None:
            self.live_button.setEnabled(not running)
            self.export_button.setEnabled(not running)
            self.cancel_button.setEnabled(running)

        def _live_scan_completed(self, value: object) -> None:
            worker = self._scan_worker
            self._scan_worker = None
            self._set_scan_controls(running=False)
            capture = cast(ScanCapture, value)
            self.sessions.insert(0, capture.session)
            self._populate_sessions()
            self.session_list.setCurrentRow(0)
            saved = f" Saved to {capture.saved_path.name}." if capture.saved_path else ""
            self.status.setText(
                f"Live scan {capture.report.state.value}: "
                f"{len(capture.report.results)} bounded responses.{saved}"
            )
            if worker is not None:
                worker.deleteLater()

        def _live_scan_failed(self, message: str) -> None:
            worker = self._scan_worker
            self._scan_worker = None
            self._set_scan_controls(running=False)
            self.status.setText("Live scan could not start.")
            QMessageBox.critical(self, "Live scan failed", message)
            if worker is not None:
                worker.deleteLater()

        def closeEvent(self, event: QCloseEvent) -> None:
            if self._scan_worker is not None:
                QMessageBox.information(
                    self,
                    "Scan still running",
                    "Stop the live scan and wait for its saved evidence before closing.",
                )
                event.ignore()
                return
            event.accept()

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
    resolved_storage_root = Path(storage_root) if storage_root else default_storage_root()
    sessions: list[DiagnosticSession] = []
    sessions = SessionStore(resolved_storage_root).list_sessions()
    if not sessions:
        sessions = [build_demo_session()]
    window = SessionViewer(sessions, storage_root=resolved_storage_root)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
