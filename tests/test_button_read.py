import contextlib
import copy
from dataclasses import replace
import errno
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import button_read as transport
from evofox_blaze import feature_read as feature
from evofox_blaze.button_capture import decode_button_capture, decode_button_journal
from evofox_blaze.buttons import describe_block
from evofox_blaze.read_preview import Delay, GetFeature, SetFeature
from evofox_blaze.state_read import IDENTITY, GET_FEATURE, SET_FEATURE


BASELINE = (Path(__file__).resolve().parents[1]
            / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json")
SYNTHETIC = bytes.fromhex("21 22 23 24 25 35 00 26")


class FakeButtons:
    def setUp(self):
        baseline, _ = feature.load_baseline(BASELINE)
        self.target = replace(baseline, path="/dev/hidraw42")
        self.events = []
        self.features = []
        self.overrides = {}
        self.reply_report = 7
        self.change_set = False
        self.descriptor = self.target.descriptor
        self.raw_info = (3, self.target.vid, self.target.pid)

    def record(self, event, **fields):
        self.events.append({"event": event, **fields})

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        if request == feature.HIDIOCGRAWINFO:
            buffer[:] = struct.pack("=IHH", *self.raw_info)
            return 0
        if request == feature.HIDIOCGRDESCSIZE:
            buffer[:] = struct.pack("=I", len(self.descriptor))
            return 0
        if request == feature.HIDIOCGRDESC:
            buffer[:4] = struct.pack("=I", len(self.descriptor))
            buffer[4:4 + len(self.descriptor)] = self.descriptor
            return 0
        self.assertIn(request, (SET_FEATURE, GET_FEATURE))
        self.assertEqual(self.events[-1]["event"], "button_feature_intent")
        self.assertEqual(self.events[-1]["buffer_hex"], buffer.hex(" "))
        self.features.append((request, bytes(buffer)))
        ordinal = len(self.features)
        if request == GET_FEATURE:
            self.assertEqual(buffer, b"\x07" + bytes(7))
            index = (ordinal - 11) // 2
            buffer[:] = bytes((self.reply_report, SYNTHETIC[index], 0x62, 9, 0xf, 0, 0x27, 0xdb))
        elif self.change_set:
            buffer[6] ^= 1
        override = self.overrides.get(ordinal, 8)
        if isinstance(override, Exception):
            raise override
        return override

    @contextlib.contextmanager
    def fake_device(self):
        with patch.object(transport, "check_host"), patch.object(feature, "check_host"), \
                patch.object(feature.os, "open", return_value=42) as opened, \
                patch.object(feature.os, "fstat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
                patch.object(feature.os, "close") as closed, patch("fcntl.flock") as locked, \
                patch("fcntl.ioctl", side_effect=self.ioctl), patch.object(transport.time, "sleep") as sleep:
            yield opened, closed, locked, sleep

    def run_read(self, record=None, recheck=None):
        with self.fake_device():
            return transport.read_buttons_once(self.target, record or self.record, recheck or Mock(),
                                                accept_staged_read_risk=True)

class ButtonReadTests(FakeButtons, unittest.TestCase):
    def test_literal_fixed_sequence_has_18_sets_8_gets_and_no_commit(self):
        recheck = Mock()
        with self.fake_device() as (opened, closed, locked, sleep):
            actual = transport.read_buttons_once(self.target, self.record, recheck, accept_staged_read_risk=True)
        self.assertEqual(actual, SYNTHETIC)
        expected = [(SET_FEATURE, bytes((7, 0x18, 3, i, 8, 0, 0, 7))) for i in range(8)]
        expected.append((SET_FEATURE, bytes.fromhex("07 18 00 00 08 00 00 00")))
        for i in range(8):
            expected.extend(((SET_FEATURE, bytes((7, 0x18, 5, i, 8, 0, 0, 7))),
                             (GET_FEATURE, b"\x07" + bytes(7))))
        expected.append((SET_FEATURE, bytes.fromhex("07 18 00 00 00 00 00 00")))
        self.assertEqual(self.features, expected)
        self.assertEqual(len(sleep.call_args_list), 18)
        self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list), 0.036)
        self.assertEqual(opened.call_args.args[1] & feature.os.O_ACCMODE, feature.os.O_RDWR)
        self.assertTrue(opened.call_args.args[1] & feature.os.O_NOFOLLOW)
        closed.assert_called_once_with(42)
        locked.assert_called_once()
        recheck.assert_called_once_with(self.target)

    def test_planner_returns_immutable_steps_with_no_address_or_length_parameter(self):
        self.assertIsInstance(transport.button_read_steps(), tuple)
        self.assertEqual(sum(isinstance(step, SetFeature) for step in transport.button_read_steps()), 18)
        self.assertEqual(sum(isinstance(step, GetFeature) for step in transport.button_read_steps()), 8)
        with self.assertRaises(TypeError):
            transport.button_read_steps(0x3f)

    def test_explicit_risk_and_exact_identity_are_checked_before_open(self):
        with patch.object(feature.os, "open") as opened:
            for consent in (False, 1, None, "yes"):
                with self.subTest(consent=consent), self.assertRaises(ValueError):
                    transport.read_buttons_once(self.target, self.record, Mock(), accept_staged_read_risk=consent)
            for change in ({"vid": 0xffff}, {"pid": 0x1e01}, {"revision": "0101"},
                           {"interface": "00"}, {"report_length": 16}, {"descriptor": bytes(8)}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    transport.read_buttons_once(replace(self.target, **change), self.record, Mock(),
                                                accept_staged_read_risk=True)
        opened.assert_not_called()

    def test_handle_mismatch_or_failed_recheck_performs_no_features(self):
        self.raw_info = (3, 0xffff, 0x1440)
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(self.features, [])
        self.raw_info = (3, 0x30fa, 0x1440)
        with self.assertRaises(ValueError):
            self.run_read(recheck=Mock(side_effect=ValueError("synthetic disconnected")))
        self.assertEqual(self.features, [])
        self.descriptor = bytes((0,)) + self.descriptor[1:]
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(self.features, [])

    def test_failed_intent_or_result_at_every_ordinal_stops_without_cleanup(self):
        for kind in ("button_feature_intent", "button_feature_result"):
            for ordinal in range(1, 27):
                self.features.clear()
                self.events.clear()
                def failed(event, **fields):
                    if event == kind and fields["ordinal"] == ordinal:
                        raise OSError(errno.ENOSPC, "synthetic full disk")
                    self.record(event, **fields)
                with self.subTest(kind=kind, ordinal=ordinal), self.assertRaises(OSError):
                    self.run_read(record=failed)
                self.assertEqual(len(self.features), ordinal - (kind == "button_feature_intent"))

    def test_short_boolean_oversized_stall_or_changed_result_aborts_once(self):
        for ordinal in (1, 9, 11, 26):
            for result in (0, 7, 9, True, OSError(errno.EPIPE, "synthetic stall")):
                self.features.clear()
                self.events.clear()
                self.overrides = {ordinal: result}
                with self.subTest(ordinal=ordinal, result=result), self.assertRaises((ValueError, OSError)):
                    self.run_read()
                self.assertEqual(len(self.features), ordinal)
        self.overrides.clear()
        self.features.clear()
        self.events.clear()
        self.reply_report = 6
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(len(self.features), 11)
        self.features.clear()
        self.events.clear()
        self.change_set = True
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(len(self.features), 1)


class ButtonCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        node = next(n for n in json.loads(BASELINE.read_text())["nodes"] if n["configuration_report"])
        self.node = dict(node, path="/dev/hidraw42")
        self.args = ["--read-buttons", "--accept-staged-read-risk", "--baseline", str(BASELINE),
                     "--capture", str(self.root / "capture")]

    def test_missing_consent_and_arbitrary_read_options_fail_before_enumeration(self):
        for args in ([a for a in self.args if a != "--read-buttons"],
                     [a for a in self.args if a != "--accept-staged-read-risk"],
                     self.args + ["--address", "0x10"], self.args + ["--length", "16"]):
            with patch.object(transport, "enumerate_devices") as enum, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                transport.main(args)
            enum.assert_not_called()

    def test_exclusive_capture_sanitized_journal_and_no_automatic_retry(self):
        with patch.object(transport, "enumerate_devices", return_value=[self.node]), \
                patch.object(transport, "read_buttons_once", return_value=SYNTHETIC) as read, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(transport.main(self.args), 0)
        self.assertFalse(json.loads(out.getvalue())["behavior_verified"])
        path = self.root / "capture/button-read.jsonl"
        self.assertNotIn("hidraw42", path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with patch.object(transport, "enumerate_devices", return_value=[self.node]), \
                patch.object(transport, "read_buttons_once") as read, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(transport.main(self.args), 1)
        read.assert_not_called()

    def test_failed_read_is_logged_and_not_retried(self):
        with patch.object(transport, "enumerate_devices", return_value=[self.node]), \
                patch.object(transport, "read_buttons_once", side_effect=OSError(errno.EPIPE, "synthetic stall")) as read, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(transport.main(self.args), 1)
        read.assert_called_once()
        events = [json.loads(line) for line in (self.root / "capture/button-read.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["event"], "button_failed")


class ButtonCaptureTests(FakeButtons, unittest.TestCase):
    # Reuse only the fake transport helpers, not duplicate the transport tests.
    def completed_events(self):
        self.events.clear()
        self.features.clear()
        self.record("button_session", identity=copy.deepcopy(IDENTITY), base="0x0008", length=8,
                    report_descriptor_hex=self.target.descriptor.hex(" "), accepted_staging_risk=True)
        data = self.run_read()
        self.record("button_complete", mode="experimental-button-read", **describe_block(data))
        return copy.deepcopy(self.events)

    def decode(self, events):
        return decode_button_journal(b"\n".join(json.dumps(event).encode() for event in events))

    def test_synthetic_complete_journal_validates_without_hardware(self):
        events = self.completed_events()
        with patch("fcntl.ioctl", side_effect=AssertionError("No hardware")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")):
            result = self.decode(events)
        self.assertEqual(result["collected_hex"], SYNTHETIC.hex(" "))
        self.assertEqual(result["set_feature_count"], 18)
        self.assertEqual(result["get_feature_count"], 8)
        self.assertFalse(result["behavior_verified"])

    def test_partial_failed_extra_or_altered_operations_are_refused(self):
        source = self.completed_events()
        for events in (source[:-1], source + [source[-1]], source[:4] + [{"event": "button_feature_error"}],
                       source[:3] + [source[2]] + source[3:]):
            with self.subTest(length=len(events)), self.assertRaises(ValueError):
                self.decode(events)
        for key, value in (("ordinal", True), ("returned_length", True), ("returned_length", 7),
                           ("buffer_hex_after", "06 21 00 00 00 00 00 00")):
            events = copy.deepcopy(source)
            event = next(e for e in events if e["event"] == "button_feature_result" and e["operation"] == "GET_FEATURE")
            event[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.decode(events)
        for frame in ("07 18 03 00 10 00 00 07", "07 18 09 00 08 00 00 07"):
            events = copy.deepcopy(source)
            next(e for e in events if e["event"] == "button_feature_intent")["buffer_hex"] = frame
            with self.assertRaises(ValueError):
                self.decode(events)

    def test_false_scope_descriptor_or_completion_claim_is_refused(self):
        source = self.completed_events()
        changes = ((0, "base", "0x0018"), (0, "accepted_staging_risk", False),
                   (0, "report_descriptor_hex", "00"), (-1, "collected_hex", "00 " * 8),
                   (-1, "behavior_verified", True), (-1, "physical_button_attribution_verified", True),
                   (-1, "complete_configuration_backup", True))
        for index, field, value in changes:
            events = copy.deepcopy(source)
            events[index][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.decode(events)

    def test_saved_input_symlink_or_device_node_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "synthetic.jsonl"
            path.write_bytes(b"\n".join(json.dumps(e).encode() for e in self.completed_events()))
            link = root / "link"
            link.symlink_to(path)
            self.assertEqual(decode_button_capture(path)["collected_hex"], SYNTHETIC.hex(" "))
            with self.assertRaises(ValueError):
                decode_button_capture(link)
        with self.assertRaises(ValueError):
            decode_button_capture(Path("/dev/null"))

    def test_original_live_button_capture_remains_unchanged(self):
        path = BASELINE.parents[1] / "30fa-1440-0100-button-read-01/button-read.jsonl"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "34acafc157a8bd657374782c6c13812ae531642fef6034ba73c78d1fcb57ec48")
        self.assertEqual(decode_button_capture(path)["collected_hex"], "21 22 23 2e 2e 35 00 26")
