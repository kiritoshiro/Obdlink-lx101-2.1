import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from notescan.diagnostics.decoders import (  # noqa: E402
    DecoderError,
    UnsupportedPidError,
    decode_dtc_response,
    decode_pid_response,
    decode_readiness_response,
)


class DecoderTests(unittest.TestCase):
    def test_engine_speed(self):
        item = decode_pid_response("41 0C 1A F8")
        self.assertEqual(item.pid, "010C")
        self.assertAlmostEqual(item.value, 1726.0)
        self.assertEqual(item.unit, "rpm")

    def test_fuel_trim_and_temperature(self):
        trim = decode_pid_response([0x41, 0x06, 0x90])
        coolant = decode_pid_response("41 05 7E")
        self.assertAlmostEqual(trim.value, 12.5)
        self.assertEqual(coolant.value, 86)

    def test_rejects_wrong_service_and_unknown_pid(self):
        with self.assertRaises(DecoderError):
            decode_pid_response("43 00 00")
        with self.assertRaises(UnsupportedPidError):
            decode_pid_response("41 99 00")

    def test_dtc_encoding(self):
        codes = decode_dtc_response("43 01 33 C1 23 00 00")
        self.assertEqual([item.code for item in codes], ["P0133", "U0123"])

    def test_readiness(self):
        status = decode_readiness_response("41 01 81 07 01 00")
        self.assertTrue(status.mil_on)
        self.assertEqual(status.stored_code_count, 1)
        self.assertEqual(status.monitors["misfire"], "not_ready")
        self.assertEqual(status.monitors["catalyst"], "unsupported")

        compact = decode_readiness_response([0x41, 0x01, 0x00, 0x07, 0x07])
        self.assertFalse(compact.mil_on)
        self.assertEqual(compact.stored_code_count, 0)


if __name__ == "__main__":
    unittest.main()
