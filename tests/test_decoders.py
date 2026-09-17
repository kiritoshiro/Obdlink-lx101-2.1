import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from notescan.diagnostics.decoders import (  # noqa: E402
    AdapterStatusResponse,
    DecoderError,
    UnsupportedPidError,
    decode_dtc_response,
    decode_negative_response,
    decode_pid_response,
    decode_readiness_response,
    decode_supported_pids_response,
    decode_vin_response,
    parse_hex_bytes,
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

    def test_extended_allowlisted_pids(self):
        runtime = decode_pid_response("41 1F 01 2C")
        fuel = decode_pid_response("41 2F 80")
        ambient = decode_pid_response("41 46 50")
        oil = decode_pid_response("41 5C 78")
        self.assertEqual(runtime.value, 300)
        self.assertAlmostEqual(fuel.value, 50.196, places=3)
        self.assertEqual(ambient.value, 40)
        self.assertEqual(oil.value, 80)

    def test_freeze_frame_uses_mode_02_positive_service(self):
        item = decode_pid_response("42 0C 01 F4", positive_service=0x42)
        self.assertEqual(item.value, 125.0)

    def test_supported_pid_bitmap_uses_standard_msb_first_mapping(self):
        supported = decode_supported_pids_response("41 00 80 00 00 01")
        self.assertEqual(supported, frozenset({0x01, 0x20}))

    def test_rejects_wrong_service_and_unknown_pid(self):
        with self.assertRaises(DecoderError):
            decode_pid_response("43 00 00")
        with self.assertRaises(UnsupportedPidError):
            decode_pid_response("41 99 00")

    def test_dtc_encoding(self):
        codes = decode_dtc_response("43 01 33 C1 23 00 00")
        self.assertEqual([item.code for item in codes], ["P0133", "U0123"])

    def test_pending_and_permanent_dtc_services(self):
        pending = decode_dtc_response("47 01 33 00 00", status="pending", positive_service=0x47)
        permanent = decode_dtc_response(
            "4A 01 33 00 00", status="permanent", positive_service=0x4A
        )
        self.assertEqual(pending[0].status, "pending")
        self.assertEqual(permanent[0].status, "permanent")

    def test_vin(self):
        vin = decode_vin_response(b"\x49\x02\x01WVWZZZ1JZXW000001")
        self.assertEqual(vin, "WVWZZZ1JZXW000001")

    def test_negative_response(self):
        self.assertEqual(decode_negative_response("7F 01 12"), (0x01, 0x12))
        self.assertIsNone(decode_negative_response("41 0C 00 00"))

    def test_readiness_uses_j1979_byte_layout(self):
        # 41 01 A=81 B=17 C=21 D=20
        # A: MIL on, one stored code.
        # B: bits 0-2 -> misfire/fuel/components supported; bit 4 -> misfire not complete.
        # C: bits 0 and 5 -> catalyst and oxygen sensor supported.
        # D: bit 5 -> oxygen sensor not complete; catalyst is therefore complete.
        status = decode_readiness_response("41 01 81 17 21 20")
        self.assertTrue(status.mil_on)
        self.assertEqual(status.stored_code_count, 1)
        self.assertEqual(status.monitors["misfire"], "not_ready")
        self.assertEqual(status.monitors["fuel_system"], "ready")
        self.assertEqual(status.monitors["components"], "ready")
        self.assertEqual(status.monitors["catalyst"], "ready")
        self.assertEqual(status.monitors["oxygen_sensor"], "not_ready")
        self.assertEqual(status.monitors["egr_system"], "unsupported")

    def test_readiness_continuous_monitors_are_not_read_from_the_wrong_byte(self):
        # B=07 means all three continuous monitors are supported AND complete.
        status = decode_readiness_response([0x41, 0x01, 0x00, 0x07, 0x01, 0x00])
        self.assertFalse(status.mil_on)
        self.assertEqual(status.stored_code_count, 0)
        for name in ("misfire", "fuel_system", "components", "catalyst"):
            self.assertEqual(status.monitors[name], "ready")

    def test_readiness_selects_compression_ignition_monitor_names(self):
        status = decode_readiness_response("41 01 00 0F 01 01")
        self.assertEqual(status.monitors["nmhc_catalyst"], "not_ready")
        self.assertNotIn("catalyst", status.monitors)

    def test_readiness_requires_all_four_data_bytes(self):
        with self.assertRaises(DecoderError):
            decode_readiness_response("41 01 00 07 07")

    def test_dtc_response_with_can_count_byte(self):
        codes = decode_dtc_response("43 02 01 33 01 96 00 00")
        self.assertEqual([item.code for item in codes], ["P0133", "P0196"])

    def test_dtc_response_rejects_impossible_declared_count(self):
        with self.assertRaises(DecoderError):
            decode_dtc_response("43 05 01 33 00 00 00 00")

    def test_adapter_status_replies_are_reported_separately(self):
        with self.assertRaises(AdapterStatusResponse):
            decode_pid_response("NO DATA")
        with self.assertRaises(AdapterStatusResponse):
            decode_dtc_response(b"UNABLE TO CONNECT\r")

    def test_searching_prefix_is_stripped_before_decoding(self):
        supported = decode_supported_pids_response(b"SEARCHING...\r41 00 80 00 00 01")
        self.assertEqual(supported, frozenset({0x01, 0x20}))

    def test_raw_bytes_containing_whitespace_values_are_not_reparsed_as_text(self):
        # 41 0C 0D 20 decodes as ASCII but is a raw Mode 01 PID 0C response.
        self.assertEqual(parse_hex_bytes(b"\x41\x0c\x0d\x20"), b"\x41\x0c\x0d\x20")


if __name__ == "__main__":
    unittest.main()
