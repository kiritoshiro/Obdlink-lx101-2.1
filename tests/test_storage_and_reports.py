import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from notescan.diagnostics.simulator import build_demo_session  # noqa: E402
from notescan.reports.render import render_session_html, render_session_markdown  # noqa: E402
from notescan.storage import SessionStore  # noqa: E402


class StorageAndReportTests(unittest.TestCase):
    def test_round_trip_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(directory)
            original = build_demo_session("round-trip")
            path = store.save(original)
            loaded = store.load("round-trip")
            self.assertEqual(path.name, "round-trip.json")
            self.assertEqual(loaded.to_dict(), original.to_dict())
            self.assertEqual([item.session_id for item in store.list_sessions()], ["round-trip"])

    def test_report_mentions_coverage_and_policy(self):
        session = build_demo_session()
        session.vehicle.vin = "WVWZZZ1JZXW000001"
        session.metadata = {"port": "COM7", "adapter_identity": "OBDLink LX"}
        markdown = render_session_markdown(session)
        html = render_session_html(session)
        self.assertIn("Not checked:", markdown)
        self.assertIn("No write, clear, actuator", markdown)
        self.assertIn("VIN: WVWZZZ1JZXW000001", markdown)
        self.assertIn("port: COM7", markdown)
        self.assertIn("SafeScan evidence report", html)
        self.assertIn("airbag/SRS", html)


if __name__ == "__main__":
    unittest.main()
