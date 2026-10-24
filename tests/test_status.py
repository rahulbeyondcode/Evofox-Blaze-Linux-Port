import contextlib
from dataclasses import FrozenInstanceError
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evofox_blaze.status import StandaloneStatus, decode_status_capture, main


CAPTURE = (Path(__file__).resolve().parents[1]
           / "docs/device-captures/30fa-1440-0100-get-feature-01/feature-read.jsonl")


class StatusTests(unittest.TestCase):
    def test_recorded_response_preserves_unknown_fields(self):
        result = decode_status_capture(CAPTURE)
        self.assertEqual(result["raw_response_hex"], "07 00 58 09 1f 00 23 7b")
        self.assertEqual(result["profile_index_candidate"], 0)
        self.assertEqual(result["static_initializer_observation"]["local_constant"], "0x0ff8")
        self.assertEqual(result["unknown_byte6_bits"], {"mask": "0xf3", "value": "0x23"})
        self.assertEqual(result["opaque_bytes_hex"], {"1": "00", "2": "58", "3": "09",
                                                     "4": "1f", "5": "00", "7": "7b"})
        self.assertFalse(result["hardware_field_validation"])

    def test_all_status_values_follow_only_the_proven_masks(self):
        fixture_path = Path(__file__).parent / "fixtures/status-consumer-observations.json"
        fixture = json.loads(fixture_path.read_text())
        profile = fixture["profile_index_candidate"]
        initializer = fixture["initializer_observation"]
        for value in range(256):
            raw = bytes((7, 1, 2, 3, 4, 5, value, 7))
            status = StandaloneStatus(raw)
            with self.subTest(value=value):
                self.assertEqual(status.profile_index_candidate,
                                 (value & profile["mask"]) >> profile["shift"])
                self.assertEqual(status.initializer_local_constant,
                                 initializer["set_local_constant"] if value & initializer["mask"]
                                 else initializer["clear_local_constant"])
                self.assertEqual(status.unknown_byte6_bits, value & fixture["unknown_byte6_mask"])
                self.assertEqual(status.unknown_byte6_bits | (value & profile["mask"]), value)
                self.assertEqual(status.raw, raw)

    def test_unknown_bits_do_not_change_the_profile_candidate(self):
        for profile in range(4):
            known = profile << 2
            first = StandaloneStatus(bytes([7, 0, 0, 0, 0, 0, known, 0]))
            second = StandaloneStatus(bytes([7, 255, 255, 255, 255, 255, known | 0xF3, 255]))
            self.assertEqual(first.profile_index_candidate, second.profile_index_candidate)
            self.assertEqual(first.unknown_byte6_bits, 0)
            self.assertEqual(second.unknown_byte6_bits, 0xF3)

    def test_invalid_report_shapes_are_refused(self):
        for data in (b"", bytes(7), bytes(9), bytes(8), b"\x06" + bytes(7), bytearray(8), "12345678"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                StandaloneStatus(data)

    def test_status_is_immutable(self):
        status = StandaloneStatus(b"\x07" + bytes(7))
        with self.assertRaises(FrozenInstanceError):
            status.raw = bytes(8)

    def test_cli_is_offline(self):
        output = io.StringIO()
        with patch("evofox_blaze.feature_read.get_feature_once", side_effect=AssertionError("No device reads")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No device enumeration")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(main(["--capture", str(CAPTURE)]), 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "offline-status-inspection")


class JournalValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "feature-read.jsonl"
        self.events = [json.loads(line) for line in CAPTURE.read_text().splitlines()]

    def assert_rejected(self):
        self.path.write_text("".join(json.dumps(event) + "\n" for event in self.events))
        with self.assertRaises(ValueError):
            decode_status_capture(self.path)

    def test_incomplete_failed_or_repeated_requests_are_refused(self):
        original = self.events
        for events in (original[:-1], original + [original[-1]],
                       original[:3] + [{"event": "get_feature_error"}],
                       original[:3] + [original[2]] + original[3:]):
            self.events = events
            with self.subTest(events=events):
                self.assert_rejected()

    def test_wrong_request_context_is_not_decoded_as_standalone_status(self):
        self.events[2]["request_buffer_hex"] = "07 18 05 00 18 00 00 07"
        self.assert_rejected()

    def test_descriptor_hash_and_handle_identity_must_match(self):
        self.events[0]["identity"]["report_descriptor_sha256"] = "bad"
        self.assert_rejected()
        self.events[1]["identity"]["report_descriptor_sha256"] = "bad"
        self.assert_rejected()

    def test_descriptor_cannot_be_replaced_by_a_different_report_layout(self):
        import hashlib
        descriptor = bytes.fromhex("06 01 ff 09 01 a1 01 85 07 75 08 95 0f b1 02 c0")
        self.events[0]["report_descriptor_hex"] = descriptor.hex(" ")
        digest = hashlib.sha256(descriptor).hexdigest()
        for index in (0, 1):
            self.events[index]["identity"]["report_descriptor_sha256"] = digest
        self.assert_rejected()

    def test_other_vendor_device_is_not_interpreted_as_blaze_status(self):
        for index in (0, 1):
            self.events[index]["identity"]["vid"] = "ffff"
        self.assert_rejected()

    def test_short_or_inconsistent_completions_are_refused(self):
        self.events[3]["returned_length"] = 7
        self.assert_rejected()
        self.events[3]["returned_length"] = 8
        self.events[-1]["response_hex"] = "07 00 00 00 00 00 00 00"
        self.assert_rejected()

    def test_cli_reports_corrupt_journal_without_any_device_access(self):
        self.path.write_text("not json\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--capture", str(self.path)]), 1)


if __name__ == "__main__":
    unittest.main()
