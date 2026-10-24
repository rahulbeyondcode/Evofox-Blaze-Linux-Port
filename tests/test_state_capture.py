import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from evofox_blaze.capture_view import present_capture
from evofox_blaze.read_preview import decode_state_block
from evofox_blaze.state_capture import decode_state_capture, decode_state_journal, main


CAPTURE = (Path(__file__).resolve().parents[1]
           / "docs/device-captures/30fa-1440-0100-state-read-01/state-read.jsonl")


class StateCaptureTests(unittest.TestCase):
    def setUp(self):
        self.raw = CAPTURE.read_bytes()
        self.events = [json.loads(line) for line in self.raw.splitlines()]

    def decode(self, events):
        return decode_state_journal(b"\n".join(json.dumps(event).encode() for event in events))

    def test_actual_capture_is_complete_and_original_bytes_are_unchanged(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),
                         "52962a834aa2f4f51974c260d8bc536f01688e51e5a970eafaf6df6d50dc987f")
        result = decode_state_capture(CAPTURE)
        self.assertEqual(result["collected_hex"], "19 3f 32 00 f3 ff 01 00")
        self.assertEqual(result["dpi_stage_selector_candidate"], 1)
        self.assertEqual(result["enabled_stage_indices_candidate"], list(range(6)))
        self.assertEqual(result["polling_divisor_raw"], 1)
        self.assertEqual(result["usb_speed_index_candidate"], 2)
        self.assertEqual(result["polling_hz_candidate"], 500)
        self.assertIsNone(result["dpi_cpi"])
        self.assertFalse(result["complete_configuration_backup"])
        self.assertFalse(result["polling_frequency_measured"])

    def test_failed_incomplete_repeated_or_extra_events_are_not_a_success(self):
        for events in (self.events[:-1], self.events + [self.events[-1]],
                       self.events[:4] + [{"event": "state_feature_error"}],
                       self.events[:3] + [self.events[2]] + self.events[3:]):
            with self.subTest(events=len(events)), self.assertRaises(ValueError):
                self.decode(events)

    def test_added_commit_cannot_be_presented_as_a_state_read(self):
        events = copy.deepcopy(self.events)
        request = next(event for event in events if event["event"] == "state_feature_intent")
        request["buffer_hex"] = "07 18 09 00 18 00 00 07"
        with self.assertRaises(ValueError):
            self.decode(events)

    def test_identity_descriptor_and_scope_must_match(self):
        for field, value in (("base", "0x003f"), ("length", 16), ("accepted_staging_risk", False),
                             ("report_descriptor_hex", "00")):
            events = copy.deepcopy(self.events)
            events[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.decode(events)
        events = copy.deepcopy(self.events)
        events[1]["identity"]["pid"] = "1e01"
        with self.assertRaises(ValueError):
            self.decode(events)

    def test_short_or_wrong_report_responses_and_wrong_ordinals_are_refused(self):
        for field, value in (("returned_length", 7), ("returned_length", True), ("ordinal", 99),
                             ("buffer_hex_after", "06 19 62 09 0f 00 27 db")):
            events = copy.deepcopy(self.events)
            result = next(event for event in events if event["event"] == "state_feature_result"
                          and event["operation"] == "GET_FEATURE")
            result[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.decode(events)

    def test_false_completion_or_full_backup_claim_is_refused(self):
        for field, value in (("collected_hex", "00 00 00 00 00 00 00 00"),
                             ("dpi_stage_selector_candidate", 5), ("complete_configuration_backup", True)):
            events = copy.deepcopy(self.events)
            events[-1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.decode(events)

    def test_saved_inspection_and_gui_do_not_contact_a_device(self):
        with patch("fcntl.ioctl", side_effect=AssertionError("No hardware access")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--capture", str(CAPTURE)]), 0)
            rows = dict(present_capture(CAPTURE).rows)
        self.assertEqual(rows["Captured state block"], "19 3f 32 00 f3 ff 01 00")
        self.assertNotIn("Profile index candidate", rows)
        self.assertIn("not measured", rows["Polling setting candidate"])
        self.assertEqual(json.loads(output.getvalue())["set_feature_count"], 18)

    def test_unknown_stage_mask_bits_and_divisors_are_not_clamped(self):
        for value in range(256):
            block = bytes((value, value, 0, 0, 0, 0, value, 0))
            result = decode_state_block(block)
            self.assertEqual(result["dpi_stage_selector_candidate"], value & 7)
            self.assertEqual(result["unassigned_enable_mask_bits_hex"], f"{value & 0xC0:02x}")
            self.assertEqual(result["polling_divisor_raw"], value)
            if value not in (0, 1, 3, 7):
                self.assertIsNone(result["polling_hz_candidate"])


if __name__ == "__main__":
    unittest.main()
