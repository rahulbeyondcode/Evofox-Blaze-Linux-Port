import json
import contextlib
import io
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

from evofox_blaze import assignment_read as read
from evofox_blaze.feature_read import Journal
from evofox_blaze.state_read import IDENTITY, SET_FEATURE, GET_FEATURE
from test_shortcut_write import FakeShortcutMouse


class AssignmentReadTests(FakeShortcutMouse, unittest.TestCase):
    def collect_read(self):
        self.capture.mkdir()
        original_record = Journal.record
        def emit(journal, event, **fields):
            self.last_event = event, fields
            return original_record(journal, event, **fields)
        with patch.object(read, "validated_handle", side_effect=self.handle), patch.object(read, "check_host"), \
                patch.object(Journal, "record", emit), patch("fcntl.ioctl", side_effect=self.ioctl), \
                patch("time.sleep"), patch("os.fsync"):
            with JournalContext(self.capture / "assignments.jsonl") as journal:
                journal.record("assignment_read_session", identity=IDENTITY,
                               report_descriptor_hex=self.target.descriptor.hex(" "), accepted_staging_risk=True,
                               scope="blaze-shortcut-assignments-v1")
                blocks = read.read_assignments_once(self.target, journal.record, Mock(), accept_staged_read_risk=True)
                result = read.summary(blocks)
                journal.record("assignment_read_complete", **result)
        return result

    def test_original_active_records_are_decoded_without_a_commit(self):
        self.memory[11] = self.memory[12] = 0x2e  # Original slot-4/5 shortcut links.
        result = self.collect_read()
        self.assertEqual(result["block_count"], 81)
        self.assertEqual(result["settings_commits"], 0)
        self.assertEqual(result["set_feature_count"], 1458)
        self.assertEqual(result["get_feature_count"], 648)
        self.assertEqual(result["verified_shortcuts"], [
            {"slot": 4, "key": "Left", "modifiers": ["Control_L", "Super_L"]},
            {"slot": 5, "key": "Right", "modifiers": ["Control_L", "Super_L"]}])
        self.assertEqual(self.commits, 0)
        self.assertEqual(sum(request == SET_FEATURE for request, _ in self.features), 1458)
        self.assertEqual(sum(request == GET_FEATURE for request, _ in self.features), 648)
        decoded = read.decode_assignment_capture(self.capture / "assignments.jsonl")
        self.assertEqual(decoded["verified_shortcuts"], result["verified_shortcuts"])

    def test_owned_tail_chords_and_native_actions_are_read_without_writes(self):
        self.change()
        self.capture = self.root / "read"
        previous = dict(self.memory)
        self.features.clear()
        result = self.collect_read()
        self.assertEqual(result["block_count"], 86)
        self.assertEqual(result["verified_shortcuts"], [{"slot": 5, "key": "F13", "modifiers": []}])
        self.assertEqual(self.memory, previous)
        self.assertTrue(all(frame[2] != 9 for request, frame in self.features if request == SET_FEATURE))
        read.decode_assignment_capture(self.capture / "assignments.jsonl")

    def test_consent_unknown_layout_and_failure_never_commit_or_retry(self):
        with patch.object(read, "validated_handle") as opened:
            for consent in (False, 1, None):
                with self.assertRaises(ValueError):
                    read.read_assignments_once(self.target, Mock(), Mock(), accept_staged_read_risk=consent)
        opened.assert_not_called()
        self.memory[0x6e] = 0
        with self.assertRaisesRegex(ValueError, "allocation layout"):
            self.collect_read()
        self.assertEqual(self.commits, 0)
        self.assertTrue(all(int.from_bytes(frame[4:6], 'little') < 0x400
                            for request, frame in self.features if request == SET_FEATURE))

    def test_incomplete_false_claim_and_extra_operation_are_rejected_offline(self):
        self.collect_read()
        path = self.capture / "assignments.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        encode = lambda rows: b"\n".join(json.dumps(event).encode() for event in rows)
        for rows in (events[:-1], events + [events[-1]]):
            with self.assertRaises(ValueError):
                read.decode_assignment_journal(encode(rows))
        events[-1]["settings_commits"] = 1
        with self.assertRaises(ValueError):
            read.decode_assignment_journal(encode(events))

    def test_cli_requires_scope_optins_and_has_no_arbitrary_range_before_enumeration(self):
        from test_shortcut_write import BASELINE
        args = ["--read-assignments", "--accept-staged-read-risk", "--baseline", str(BASELINE),
                "--capture", "/synthetic/new-read"]
        for variant in (args[1:], [value for value in args if value != "--accept-staged-read-risk"],
                        args + ["--address", "0x10"]):
            with patch.object(read, "enumerate_devices") as enumerate_devices, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                read.main(variant)
            enumerate_devices.assert_not_called()

    def test_first_transport_failure_stops_without_retry_or_commit(self):
        with patch.object(read, "validated_handle", side_effect=self.handle), patch.object(read, "check_host"), \
                patch("fcntl.ioctl", side_effect=OSError("Synthetic failure")) as ioctl, \
                patch("time.sleep"), self.assertRaises(OSError):
            read.read_assignments_once(self.target, Mock(), Mock(), accept_staged_read_risk=True)
        ioctl.assert_called_once()


class JournalContext:
    def __init__(self, path):
        self.journal = Journal(path)

    def __enter__(self):
        return self.journal

    def __exit__(self, *args):
        self.journal.close()
